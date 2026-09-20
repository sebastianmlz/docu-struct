"""Central API router aggregating all versioned endpoints."""

from fastapi import APIRouter

from src.api.v1.documents import router as documents_router
from src.core.config import settings

api_router = APIRouter(prefix="/api/v1")

# Inclusión de submódulos
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])


@api_router.get("/health", tags=["system"], summary="Verificar Estado de Salud de la API")
async def health_check():
    """Retorna información de diagnóstico del microservicio y estado de dependencias."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "llm_configured": settings.is_llm_configured,
        "provider": settings.get_provider_for_model(settings.OPENAI_MODEL),
        "active_model": settings.OPENAI_MODEL,
        "max_pages_limit": settings.MAX_PAGES_PER_DOCUMENT,
        "pdf_dpi": settings.PDF_RENDER_DPI,
    }
