"""Unit tests for structured JSON logging and X-Request-ID trace propagation."""

import json
import logging

from fastapi.testclient import TestClient

from src.core.logging import (
    RequestIdFilter,
    StructuredJSONFormatter,
    get_request_id,
    set_request_id,
    setup_logging,
)
from src.main import app

client = TestClient(app)


def test_request_id_context_and_filter():
    """Valida la inyección del request_id en ContextVar y su filtro de logging."""
    set_request_id("test-corr-uuid-456")
    assert get_request_id() == "test-corr-uuid-456"

    log_filter = RequestIdFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Mensaje de prueba",
        args=(),
        exc_info=None,
    )
    assert log_filter.filter(record) is True
    assert record.request_id == "test-corr-uuid-456"


def test_structured_json_formatter():
    """Valida que StructuredJSONFormatter genere un JSON parseable con los campos obligatorios."""
    set_request_id("req-json-abc")
    formatter = StructuredJSONFormatter()

    record = logging.LogRecord(
        name="docustruct.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=42,
        msg="Alerta de prueba: %s",
        args=("recurso saturado",),
        exc_info=None,
    )
    record.request_id = "req-json-abc"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "WARNING"
    assert parsed["logger"] == "docustruct.test"
    assert parsed["message"] == "Alerta de prueba: recurso saturado"
    assert parsed["request_id"] == "req-json-abc"
    assert "timestamp" in parsed
    assert parsed["lineno"] == 42


def test_structured_json_formatter_with_exception():
    """Valida la inclusión de tracebacks en el payload JSON estructurado."""
    formatter = StructuredJSONFormatter()
    try:
        raise ValueError("Error forzado de prueba")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="docustruct.error",
            level=logging.ERROR,
            pathname=__file__,
            lineno=80,
            msg="Fallo inesperado",
            args=(),
            exc_info=sys.exc_info(),
        )

    output = formatter.format(record)
    parsed = json.loads(output)
    assert "exception" in parsed
    assert "ValueError: Error forzado de prueba" in parsed["exception"]


def test_x_request_id_in_http_response_headers():
    """Valida que cada respuesta HTTP contenga la cabecera X-Request-ID generada automáticamente."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 10


def test_custom_x_request_id_is_preserved_and_propagated():
    """Valida que si el cliente envía su propio X-Request-ID, el servidor lo preserve y lo devuelva."""
    custom_id = "client-trace-777-abc"
    response = client.get("/api/v1/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


def test_structured_json_formatter_with_extra_fields():
    """Valida que los campos extra arbitrarios se incluyan en el payload JSON."""
    formatter = StructuredJSONFormatter()
    record = logging.LogRecord(
        name="docustruct.extra",
        level=logging.INFO,
        pathname=__file__,
        lineno=105,
        msg="Operación completada",
        args=(),
        exc_info=None,
    )
    record.client_ip = "192.168.1.50"
    record.document_pages = 7

    output = formatter.format(record)
    parsed = json.loads(output)
    assert "extra" in parsed
    assert parsed["extra"]["client_ip"] == "192.168.1.50"
    assert parsed["extra"]["document_pages"] == 7


def test_setup_logging_json_mode_and_console_mode():
    """Valida que setup_logging configure correctamente los handlers en modo JSON y texto."""
    from unittest.mock import patch

    from src.core.config import settings

    with patch.object(settings, "JSON_LOGS_ENABLED", True):
        setup_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, StructuredJSONFormatter)

    with patch.object(settings, "JSON_LOGS_ENABLED", False):
        setup_logging()
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, StructuredJSONFormatter)

