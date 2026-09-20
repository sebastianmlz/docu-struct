import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.router import api_router
from src.core.config import settings
from src.core.logging import set_request_id, setup_logging
from src.core.security import concurrency_guard
from src.core.telemetry import telemetry_registry
from src.web.router import web_router

logger = logging.getLogger("docustruct.main")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: configuración al arranque y cierre ordenado (graceful shutdown)."""
    setup_logging()
    logger.info("=========================================================")
    logger.info("Iniciando %s (v%s)", settings.PROJECT_NAME, settings.VERSION)
    logger.info("Modelo LLM Activo: %s", settings.OPENAI_MODEL)
    logger.info("Límites: Máx %d págs, %d MB", settings.MAX_PAGES_PER_DOCUMENT, settings.MAX_UPLOAD_SIZE_MB)
    logger.info("DPI de Renderizado: %d DPI", settings.PDF_RENDER_DPI)
    logger.info("Caché Idempotente: %s (Max: %d docs, TTL: %ds)", settings.CACHE_ENABLED, settings.CACHE_MAX_ENTRIES, settings.CACHE_TTL_SECONDS)
    logger.info("Métricas Prometheus: %s (/metrics)", settings.METRICS_ENABLED)
    if settings.is_gemini_configured:
        logger.info("API Key de Google Gemini: Configurada [OK]")
    if settings.is_openai_configured:
        logger.info("API Key de OpenAI: Configurada [OK]")
    if not settings.is_llm_configured:
        logger.warning("No hay API Key configurada para el proveedor activo (%s)", settings.get_provider_for_model(settings.OPENAI_MODEL))
    logger.info("=========================================================")

    yield

    logger.info("Iniciando apagado ordenado (graceful shutdown) de %s...", settings.PROJECT_NAME)
    await concurrency_guard.drain(timeout_seconds=float(settings.GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS))
    logger.info("Cierre completado. Recursos liberados con éxito.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Microservicio industrial para extracción forense y estructuración de documentos heterogéneos.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ------------------------------------------------------------------------------
# Observabilidad: Trazabilidad por Request-ID y Telemetría
# ------------------------------------------------------------------------------
@app.middleware("http")
async def telemetry_and_request_id_middleware(request: Request, call_next):
    """Correlaciona cada petición con un X-Request-ID unívoco y mide la latencia para métricas."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(request_id)
    start_time = time.perf_counter()

    try:
        response: Response = await call_next(request)
    finally:
        duration = time.perf_counter() - start_time
        # Si la respuesta existe, registrar en telemetría; si falló antes de responder, registrar 500
        status_code = getattr(locals().get("response"), "status_code", 500)
        telemetry_registry.record_request(
            method=request.method,
            endpoint=request.url.path,
            status_code=status_code,
            duration_seconds=duration,
        )

    response.headers["X-Request-ID"] = request_id
    return response


# ------------------------------------------------------------------------------
# Hardening de Seguridad: Cabeceras HTTP de Protección
# ------------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Inyecta cabeceras defensivas contra sniffing, clickjacking, inyecciones y fugas de contexto."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

    if settings.STRICT_CSP_ENABLED:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none';"
        )
    return response


# ------------------------------------------------------------------------------
# Configuración de CORS Controlado
# ------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montaje de archivos estáticos (JS nativo, CSS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Montaje de rutas web y rutas API
app.include_router(web_router)
app.include_router(api_router)


# ------------------------------------------------------------------------------
# Endpoints de Telemetría y Métricas (Prometheus & JSON)
# ------------------------------------------------------------------------------
@app.get(
    "/metrics",
    response_class=Response,
    summary="Métricas de observabilidad en formato estándar Prometheus (v0.0.4)",
    tags=["Telemetría"],
)
async def prometheus_metrics():
    """Exporta métricas operacionales de concurrencia, peticiones, latencia y caché para Prometheus."""
    if not settings.METRICS_ENABLED:
        return Response(content="Métricas deshabilitadas.\n", status_code=404, media_type="text/plain")
    exposition = telemetry_registry.generate_prometheus_exposition()
    return Response(content=exposition, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get(
    "/api/v1/telemetry",
    summary="Resumen operacional en formato JSON",
    tags=["Telemetría"],
)
async def json_telemetry():
    """Retorna estado y estadísticas operacionales en formato JSON."""
    return telemetry_registry.to_json()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main.py:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
