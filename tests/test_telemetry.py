"""Unit tests for the in-memory telemetry and Prometheus metrics collector."""

from fastapi.testclient import TestClient

from src.core.telemetry import InMemoryMetricsRegistry
from src.main import app

client = TestClient(app)


def test_telemetry_registry_record_methods():
    """Valida los métodos de registro atómico del colector de telemetría."""
    reg = InMemoryMetricsRegistry()

    reg.record_request("POST", "/api/v1/documents/process", 200, 0.45)
    reg.record_request("GET", "/api/v1/health", 200, 0.01)
    reg.set_active_concurrency(2)
    reg.record_document_processed(pages_count=4)
    reg.record_cache_hit()
    reg.record_cache_miss()
    reg.record_ratelimit_rejection()
    reg.record_concurrency_rejection()
    reg.record_model_retry()

    summary = reg.to_json()
    assert summary["active_concurrency_jobs"] == 2
    assert summary["total_documents_processed"] == 1
    assert summary["total_pages_rasterized"] == 4
    assert summary["cache"]["hits"] == 1
    assert summary["cache"]["misses"] == 1
    assert summary["security_rejections"]["ratelimit_429"] == 1
    assert summary["security_rejections"]["concurrency_503"] == 1
    assert summary["model_retries"] == 1
    assert len(summary["requests"]) >= 2


def test_prometheus_exposition_format():
    """Valida la generación de métricas compatibles con el estándar de texto plano de Prometheus."""
    reg = InMemoryMetricsRegistry()
    reg.record_request("POST", "/api/v1/documents/process", 200, 1.25)
    reg.record_cache_hit()

    expo = reg.generate_prometheus_exposition()
    assert "# HELP docustruct_uptime_seconds" in expo
    assert "# TYPE docustruct_uptime_seconds gauge" in expo
    assert "docustruct_concurrency_active_jobs 0" in expo
    assert "docustruct_cache_hits_total 1" in expo
    assert 'docustruct_http_requests_total{method="POST",endpoint="/api/v1/documents/process",status="200"} 1' in expo
    assert "docustruct_http_request_duration_seconds_bucket" in expo
    assert expo.endswith("\n")


def test_http_endpoint_metrics():
    """Valida la respuesta del endpoint público /metrics a través de HTTP."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "docustruct_uptime_seconds" in response.text
    assert "docustruct_concurrency_active_jobs" in response.text


def test_http_endpoint_telemetry_json():
    """Valida la respuesta del endpoint de telemetría en JSON /api/v1/telemetry."""
    response = client.get("/api/v1/telemetry")
    assert response.status_code == 200
    payload = response.json()
    assert "uptime_seconds" in payload
    assert "active_concurrency_jobs" in payload
    assert "cache" in payload
    assert "requests" in payload
