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
