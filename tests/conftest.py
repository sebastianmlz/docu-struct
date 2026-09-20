"""Pytest shared fixtures and test configuration."""

import pytest

from src.core.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Fixture para settings en entorno de testing."""
    return Settings(
        DEBUG=True,
        OPENAI_API_KEY="sk-test-key-mock-12345",
        MAX_UPLOAD_SIZE_MB=5,
        MAX_PAGES_PER_DOCUMENT=5,
        PDF_RENDER_DPI=72,
    )


@pytest.fixture(autouse=True)
def reset_in_memory_state():
    """Limpia el estado en memoria de rate limiter y caché entre cada test para evitar interferencias."""
    from src.core.cache import document_cache
    from src.core.security import rate_limiter

    with rate_limiter._lock:
        rate_limiter._requests.clear()
    document_cache.clear()
    yield
    with rate_limiter._lock:
        rate_limiter._requests.clear()
    document_cache.clear()

