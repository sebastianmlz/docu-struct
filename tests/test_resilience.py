"""Unit tests for resilience, jitter retries, idempotent caching in /process, and graceful shutdown."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.core.cache import document_cache
from src.core.security import ConcurrencyGuard, ServerCapacityExceededError
from src.core.telemetry import telemetry_registry
from src.main import app
from src.schemas.document import PageExtraction
from src.services.pdf_converter import RenderedDocument, RenderedPage
from src.services.vision_extractor import VisionExtractorService

client = TestClient(app)


@pytest.mark.asyncio
async def test_concurrency_guard_drain_and_shutdown():
    """Valida el drenado ordenado de trabajos concurrentes y el rechazo de nuevas peticiones."""
    guard = ConcurrencyGuard(max_slots=2)

    # 1. Adquirir una ranura simulando un trabajo pesado en vuelo
    async with guard.acquire_slot():
        assert guard.active_jobs == 1

        # En otra corrutina, iniciar el drenado con timeout
        drain_task = asyncio.create_task(guard.drain(timeout_seconds=2.0))
        await asyncio.sleep(0.05)

        # Intentar adquirir otra ranura durante el drenado debe fallar de inmediato
        with pytest.raises(ServerCapacityExceededError) as exc_info:
            async with guard.acquire_slot():
                pass
        assert "apagado ordenado" in str(exc_info.value)

        # Liberar la ranura saliendo del context manager
        await asyncio.sleep(0.1)

    # El drenado debe completarse exitosamente
    drain_result = await drain_task
    assert drain_result is True
    assert guard.active_jobs == 0
    assert guard.is_shutting_down is True


def test_idempotent_cache_hit_on_process_endpoint():
    """Valida que una petición idéntica se sirva desde la caché con cabecera X-Cache-Status: HIT."""
    document_cache.clear()
    dummy_pdf_content = b"%PDF-1.4 \n%idempotent-test-content-stream\n%%EOF"

    mock_page_extraction = PageExtraction(page_number=1, blocks=[])
    mock_rendered_doc = RenderedDocument(
        total_pages=1,
        dpi=150,
        pages=[RenderedPage(page_number=1, image_base64_uri="data:image/jpeg;base64,mock", width_px=800, height_px=600)],
    )

    with (
        patch("src.services.pdf_converter.PDFConverterService.convert", return_value=mock_rendered_doc),
        patch("src.services.vision_extractor.VisionExtractorService.aextract_page", new_callable=AsyncMock) as mock_extract,
    ):
        mock_extract.return_value = mock_page_extraction

        # 1ra petición: Debe ser un MISS de caché y ejecutar el modelo
        files = {"file": ("reporte_idempotente.pdf", dummy_pdf_content, "application/pdf")}
        resp1 = client.post("/api/v1/documents/process", files=files)

        assert resp1.status_code == 200
        assert resp1.headers.get("x-cache-status") == "MISS"
        assert mock_extract.call_count == 1

        # 2da petición: Debe ser un HIT de caché y NO volver a invocar el modelo
        resp2 = client.post("/api/v1/documents/process", files=files)

        assert resp2.status_code == 200
        assert resp2.headers.get("x-cache-status") == "HIT"
        # La cuenta de llamadas al LLM debe permanecer en 1 (cero consumo adicional)
        assert mock_extract.call_count == 1
        assert "recuperado desde la caché idempotente" in resp2.json()["message"]


@pytest.mark.asyncio
async def test_vision_extractor_full_jitter_retry_on_429():
    """Valida que ante una respuesta 429 transitoria se aplique reintento con jitter y se registre en telemetría."""
    initial_retries = telemetry_registry.to_json()["model_retries"]

    service = VisionExtractorService()
    mock_extraction = PageExtraction(page_number=1, blocks=[])

    mock_chain = MagicMock()
    # Falla el 1er intento con RateLimitError (429) y tiene éxito en el 2do intento
    mock_chain.ainvoke = AsyncMock(
        side_effect=[
            Exception("429 Resource Exhausted / Rate limit exceeded"),
            mock_extraction,
        ]
    )

    with (
        patch.object(service, "build_lcel_chain", return_value=mock_chain),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await service.aextract_page(
            image_base64_uri="data:image/jpeg;base64,mock",
            page_number=1,
            total_pages=1,
            max_attempts=3,
        )

        assert result.page_number == 1
        assert mock_chain.ainvoke.call_count == 2
        # Validar que asyncio.sleep fue llamado para el backoff con jitter
        assert mock_sleep.call_count == 1
        # Validar que se registró en la telemetría
        assert telemetry_registry.to_json()["model_retries"] == initial_retries + 1
