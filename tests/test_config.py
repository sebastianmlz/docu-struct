"""Smoke tests for settings and environment configuration."""

from src.core.config import Settings


def test_default_settings_loaded():
    settings = Settings(_env_file=None)
    assert settings.PROJECT_NAME == "DocuStruct - Heterogeneous Document Analyzer"
    assert settings.PDF_RENDER_DPI == 150
    assert settings.MAX_UPLOAD_SIZE_MB == 25
    assert settings.max_upload_size_bytes == 25 * 1024 * 1024


def test_test_settings_fixture(test_settings: Settings):
    assert test_settings.DEBUG is True
    assert test_settings.PDF_RENDER_DPI == 72
    assert test_settings.is_openai_configured is True


def test_provider_resolution_for_different_models():
    """Valida la resolución automática de proveedor según el modelo."""
    s = Settings(_env_file=None)
    assert s.get_provider_for_model("gemini-3.8-flash") == "google"
    assert s.get_provider_for_model("gpt-5.6-terra") == "openai"
    assert s.get_provider_for_model("gpt-4o") == "openai"
