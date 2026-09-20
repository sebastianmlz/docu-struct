"""Main FastAPI application entrypoint and lifespan management."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.router import api_router
from src.core.config import settings
from src.core.logging import setup_logging
from src.web.router import web_router

logger = logging.getLogger("docustruct.main")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: configuración al arranque y cierre."""
    setup_logging()
    logger.info("=========================================================")
    logger.info("Iniciando %s (v%s)", settings.PROJECT_NAME, settings.VERSION)
    logger.info("Modelo LLM Activo: %s", settings.OPENAI_MODEL)
    logger.info("Límites: Máx %d págs, %d MB", settings.MAX_PAGES_PER_DOCUMENT, settings.MAX_UPLOAD_SIZE_MB)
    logger.info("DPI de Renderizado: %d DPI", settings.PDF_RENDER_DPI)
    if settings.is_gemini_configured:
        logger.info("API Key de Google Gemini: Configurada [OK]")
    if settings.is_openai_configured:
        logger.info("API Key de OpenAI: Configurada [OK]")
    if not settings.is_llm_configured:
        logger.warning("No hay API Key configurada para el proveedor activo (%s)", settings.get_provider_for_model(settings.OPENAI_MODEL))
    logger.info("=========================================================")

    yield

    logger.info("Cerrando %s. Liberando recursos.", settings.PROJECT_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Microservicio industrial para extracción forense y estructuración de documentos heterogéneos.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ------------------------------------------------------------------------------
# Hardening de Seguridad: Cabeceras HTTP de Protección
# ------------------------------------------------------------------------------
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Inyecta cabeceras defensivas contra sniffing, clickjacking y XSS."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main.py:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
