"""Web presentation router serving Jinja2 templates."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from src.core.config import settings

web_router = APIRouter(include_in_schema=False)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@web_router.get("/")
async def render_home(request: Request):
    """Renderiza la vista principal de la aplicación."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "model_name": settings.OPENAI_MODEL,
            "reasoning_effort": settings.OPENAI_REASONING_EFFORT,
            "max_pages": settings.MAX_PAGES_PER_DOCUMENT,
            "max_mb": settings.MAX_UPLOAD_SIZE_MB,
        },
    )
