"""Integration tests for frontend templates, static assets, and UI context."""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_home_page_serves_html():
    """Valida que la ruta GET / devuelva HTML5 con código HTTP 200."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!DOCTYPE html>" in response.text


def test_home_page_contains_expected_model_and_reasoning_context():
    """Valida que el modelo activo y el contexto se inyecten en el template."""
    from src.core.config import settings
    response = client.get("/")
    assert response.status_code == 200
    assert settings.OPENAI_MODEL in response.text
    assert "DocuStruct" in response.text
    assert 'id="dropzone"' in response.text
    assert 'id="resultsSection"' in response.text


def test_static_css_asset_is_served():
    """Valida que el archivo de estilos CSS sea servido por FastAPI StaticFiles."""
    response = client.get("/static/css/styles.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "font-feature-settings" in response.text


def test_static_js_asset_is_served_and_secure():
    """Valida que el cliente JavaScript esté disponible y contenga funciones de escape XSS."""
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"] or "text/javascript" in response.headers["content-type"]
    assert "escapeHtml" in response.text
    assert "DATO_CENSURADO" in response.text
    assert "handleFileSelection" in response.text
