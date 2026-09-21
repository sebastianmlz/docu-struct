"""Document processing REST endpoints with standalone security hardening."""

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status

from src.core.cache import document_cache
from src.core.config import settings
from src.core.security import (
    InvalidPDFMagicBytesError,
    ServerCapacityExceededError,
    concurrency_guard,
    get_client_ip,
    rate_limiter,
    sanitize_filename,
    validate_pdf_magic_bytes,
)
from src.core.telemetry import telemetry_registry
from src.schemas.api_response import (
    DocumentProcessResponse,
    ProcessingMetrics,
    ProcessingStatus,
)
from src.services.pdf_converter import (
    CorruptPDFError,
    EmptyPDFError,
    ExceededPageLimitError,
    PageDimensionExceededError,
    PDFConverterService,
)
from src.services.postprocessor import DocumentPostprocessor
from src.services.vision_extractor import (
    ExtractionModelError,
    OpenAIConfigurationError,
    VisionExtractorService,
)

logger = logging.getLogger("docustruct.api.documents")
router = APIRouter()


@router.post(
    "/process",
    response_model=DocumentProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Analizar Documento Heterogéneo (PDF)",
    description=(
        "Ingesta un archivo PDF de hasta 10 páginas, rasteriza visualmente cada página en memoria "
        "y ejecuta inferencia multimodal con LangChain LCEL para resolver tablas partidas, "
        "bloques polimórficos y celdas censuradas."
    ),
)
async def process_document(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="Archivo PDF a procesar (máximo 10 páginas)"),
) -> DocumentProcessResponse:
    """Orquestador de procesamiento de extremo a extremo con hardening de seguridad."""
    start_time = time.perf_counter()
    document_id = str(uuid.uuid4())

    # 1. Rate Limiting Autónomo por IP (Sliding Window en memoria)
    client_ip = get_client_ip(request)
    allowed, retry_after = rate_limiter.is_allowed(
        client_ip,
        max_requests=settings.RATE_LIMIT_PROCESS_PER_MINUTE,
        window_seconds=60,
    )
    if not allowed:
        logger.warning("Límite de peticiones excedido para la IP '%s' en /process", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Límite de procesamiento excedido ({settings.RATE_LIMIT_PROCESS_PER_MINUTE} peticiones/minuto). "
                f"Por favor reintenta en {retry_after} segundos."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    # 2. Sanitización Forense del Nombre de Archivo
    filename = sanitize_filename(file.filename)
    logger.info("Solicitud autorizada para procesar archivo '%s' desde IP '%s' (ID: %s)", filename, client_ip, document_id)

    # 3. Validación de Extensión
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo inválido. Se requiere un archivo PDF (.pdf), pero se recibió '{filename}'.",
        )

    # 4. Ingesta de bytes y validación de tamaño
    try:
        pdf_bytes = await file.read()
    except Exception as exc:
        logger.exception("Error al leer el stream del archivo subido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error de lectura de archivo al procesar la carga HTTP.",
        ) from exc

    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo PDF está vacío o no contiene datos.",
        )

    if len(pdf_bytes) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"El archivo excede el tamaño máximo permitido de {settings.MAX_UPLOAD_SIZE_MB} MB "
                f"(tamaño recibido: {len(pdf_bytes) / (1024 * 1024):.2f} MB)."
            ),
        )

    # 5. Validación de Magic Bytes (%PDF-)
    try:
        validate_pdf_magic_bytes(pdf_bytes)
    except InvalidPDFMagicBytesError as exc:
        logger.warning("Firma binaria inválida en archivo '%s' (IP: %s): %s", filename, client_ip, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # 6. Verificación en Caché Idempotente en RAM (SHA-256)
    cache_key = document_cache.compute_cache_key(
        pdf_bytes=pdf_bytes,
        model_name=settings.OPENAI_MODEL,
        dpi=settings.PDF_RENDER_DPI,
    )

    cached_response = document_cache.get(cache_key)
    if cached_response is not None:
        telemetry_registry.record_cache_hit()
        response.headers["X-Cache-Status"] = "HIT"
        elapsed_time = time.perf_counter() - start_time
        result_copy = cached_response.model_copy(deep=True)
        result_copy.metrics.duration_seconds = round(elapsed_time, 4)
        result_copy.message = f"Documento '{filename}' recuperado desde la caché idempotente (sin consumo de cuota LLM)."
        telemetry_registry.record_document_processed(result_copy.metrics.total_pages_processed)
        logger.info("Respuesta servida desde caché idempotente para '%s' en %.4fs", filename, elapsed_time)
        return result_copy

    telemetry_registry.record_cache_miss()
    response.headers["X-Cache-Status"] = "MISS"

    # 7. Pipeline de Ejecución con Control de Concurrencia (Anti-OOM) y Timeout Estricto
    async def _execute_analysis():
        # A. Rasterización con pypdfium2 (Zero Disk I/O)
        pdf_converter = PDFConverterService()
        rendered_doc = pdf_converter.convert(pdf_bytes)

        # B. Inferencia Multimodal: Extracción concurrente de páginas (Anti-Bottleneck)
        vision_service = VisionExtractorService()
        # Semáforo para controlar concurrencia de llamadas LLM por documento
        page_sem = asyncio.Semaphore(settings.PAGE_EXTRACTION_CONCURRENCY)

        async def _extract_single_page(page):
            async with page_sem:
                logger.info(
                    "Enviando página %d/%d al modelo multimodal (concurrente)",
                    page.page_number,
                    rendered_doc.total_pages,
                )
                return await vision_service.aextract_page(
                    image_base64_uri=page.image_base64_uri,
                    page_number=page.page_number,
                    total_pages=rendered_doc.total_pages,
                    context=None,
                    max_attempts=4,
                )

        raw_extractions = await asyncio.gather(
            *[_extract_single_page(p) for p in rendered_doc.pages]
        )
        page_extractions = sorted(raw_extractions, key=lambda p: p.page_number)

        # C. Postprocesamiento y Reconciliación Determinista
        postprocessor = DocumentPostprocessor()
        unified_result = postprocessor.process(
            document_id=document_id,
            filename=filename,
            pages=page_extractions,
        )

        return rendered_doc.total_pages, unified_result

    try:
        async with concurrency_guard.acquire_slot():
            total_pages, unified_result = await asyncio.wait_for(
                _execute_analysis(),
                timeout=settings.DOCUMENT_TIMEOUT_SECONDS,
            )

    except ServerCapacityExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
            headers={"Retry-After": "5"},
        ) from exc
    except (asyncio.TimeoutError, TimeoutError) as exc:
        logger.error("Tiempo límite excedido al procesar '%s' (%ds)", filename, settings.DOCUMENT_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"El procesamiento del documento superó el límite de seguridad de {settings.DOCUMENT_TIMEOUT_SECONDS}s.",
        ) from exc
    except (CorruptPDFError, EmptyPDFError, ExceededPageLimitError, PageDimensionExceededError) as exc:
        logger.warning("Validación de PDF fallida para '%s': %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OpenAIConfigurationError as exc:
        logger.error("Error de configuración de credenciales de IA: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ExtractionModelError as exc:
        logger.error("Fallo durante la inferencia multimodal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    elapsed_time = time.perf_counter() - start_time
    metrics = ProcessingMetrics(
        total_pages_processed=total_pages,
        duration_seconds=round(elapsed_time, 2),
        llm_model_used=settings.OPENAI_MODEL,
    )

    logger.info(
        "Documento '%s' procesado exitosamente en %.2f segundos (%d páginas)",
        filename,
        elapsed_time,
        total_pages,
    )

    final_response = DocumentProcessResponse(
        status=ProcessingStatus.SUCCESS,
        message=f"Documento '{filename}' analizado y estructurado con éxito.",
        data=unified_result,
        metrics=metrics,
    )

    telemetry_registry.record_document_processed(total_pages)
    document_cache.set(cache_key, final_response)

    return final_response
