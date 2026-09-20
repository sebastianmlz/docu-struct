"""In-memory telemetry and Prometheus-compatible metrics collector for DocuStruct.

Provides zero-dependency metrics tracking (requests, latency, concurrency, cache, and retries)
exporting both standard Prometheus text exposition format and JSON operational summaries.
"""

import threading
import time
from collections import defaultdict
from typing import Any

LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)


class InMemoryMetricsRegistry:
    """Thread-safe in-memory metrics registry for enterprise VPS observability."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()

        # Contadores por etiquetas: (method, endpoint, status_code) -> count
        self._http_requests: dict[tuple[str, str, int], int] = defaultdict(int)

        # Histogramas de duración HTTP
        self._duration_sum: float = 0.0
        self._duration_count: int = 0
        self._duration_buckets: dict[float, int] = defaultdict(int)

        # Medidores de estado (Gauges)
        self._active_concurrency_jobs: int = 0

        # Contadores de dominio
        self._documents_processed: int = 0
        self._pages_rasterized: int = 0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._ratelimit_rejections: int = 0
        self._concurrency_rejections: int = 0
        self._model_retries: int = 0

    def record_request(self, method: str, endpoint: str, status_code: int, duration_seconds: float) -> None:
        """Registra una petición HTTP procesada con su latencia."""
        with self._lock:
            # Normalizar endpoint para no fragmentar por IDs dinámicos
            clean_endpoint = endpoint.split("?")[0]
            self._http_requests[(method.upper(), clean_endpoint, status_code)] += 1

            self._duration_sum += duration_seconds
            self._duration_count += 1

            for bucket in LATENCY_BUCKETS:
                if duration_seconds <= bucket:
                    self._duration_buckets[bucket] += 1

    def set_active_concurrency(self, active_count: int) -> None:
        """Actualiza el medidor de ranuras de concurrencia ocupadas."""
        with self._lock:
            self._active_concurrency_jobs = max(0, active_count)

    def record_document_processed(self, pages_count: int) -> None:
        """Incrementa el contador de documentos completados y páginas rasterizadas."""
        with self._lock:
            self._documents_processed += 1
            self._pages_rasterized += pages_count

    def record_cache_hit(self) -> None:
        with self._lock:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        with self._lock:
            self._cache_misses += 1

    def record_ratelimit_rejection(self) -> None:
        with self._lock:
            self._ratelimit_rejections += 1

    def record_concurrency_rejection(self) -> None:
        with self._lock:
            self._concurrency_rejections += 1

    def record_model_retry(self) -> None:
        with self._lock:
            self._model_retries += 1

    def to_json(self) -> dict[str, Any]:
        """Genera un resumen en formato JSON para monitorización rápida."""
        with self._lock:
            uptime = time.time() - self._start_time
            avg_duration = (
                self._duration_sum / self._duration_count if self._duration_count > 0 else 0.0
            )

            requests_summary = [
                {"method": m, "endpoint": ep, "status": sc, "count": count}
                for (m, ep, sc), count in self._http_requests.items()
            ]

            return {
                "uptime_seconds": round(uptime, 2),
                "active_concurrency_jobs": self._active_concurrency_jobs,
                "total_documents_processed": self._documents_processed,
                "total_pages_rasterized": self._pages_rasterized,
                "cache": {
                    "hits": self._cache_hits,
                    "misses": self._cache_misses,
                },
                "security_rejections": {
                    "ratelimit_429": self._ratelimit_rejections,
                    "concurrency_503": self._concurrency_rejections,
                },
                "model_retries": self._model_retries,
                "latency_summary": {
                    "total_requests": self._duration_count,
                    "avg_duration_seconds": round(avg_duration, 4),
                    "total_duration_seconds": round(self._duration_sum, 4),
                },
                "requests": requests_summary,
            }

    def generate_prometheus_exposition(self) -> str:
        """Exporta las métricas en formato texto plano estándar de Prometheus (v0.0.4)."""
        lines: list[str] = [
            "# HELP docustruct_uptime_seconds Seconds since microservice initialization.",
            "# TYPE docustruct_uptime_seconds gauge",
        ]

        with self._lock:
            uptime = round(time.time() - self._start_time, 2)
            lines.append(f"docustruct_uptime_seconds {uptime}")

            # Medidor de Concurrencia
            lines.extend([
                "# HELP docustruct_concurrency_active_jobs Currently running in-memory heavy extraction jobs.",
                "# TYPE docustruct_concurrency_active_jobs gauge",
                f"docustruct_concurrency_active_jobs {self._active_concurrency_jobs}",
            ])

            # Contadores de Dominio
            lines.extend([
                "# HELP docustruct_documents_processed_total Total successfully processed PDF documents.",
                "# TYPE docustruct_documents_processed_total counter",
                f"docustruct_documents_processed_total {self._documents_processed}",
                "# HELP docustruct_pages_rasterized_total Total PDF pages rasterized in memory.",
                "# TYPE docustruct_pages_rasterized_total counter",
                f"docustruct_pages_rasterized_total {self._pages_rasterized}",
                "# HELP docustruct_cache_hits_total Total idempotent document cache hits.",
                "# TYPE docustruct_cache_hits_total counter",
                f"docustruct_cache_hits_total {self._cache_hits}",
                "# HELP docustruct_cache_misses_total Total idempotent document cache misses.",
                "# TYPE docustruct_cache_misses_total counter",
                f"docustruct_cache_misses_total {self._cache_misses}",
                "# HELP docustruct_ratelimit_rejections_total Total HTTP 429 rate limit rejections.",
                "# TYPE docustruct_ratelimit_rejections_total counter",
                f"docustruct_ratelimit_rejections_total {self._ratelimit_rejections}",
                "# HELP docustruct_concurrency_rejections_total Total HTTP 503 backpressure concurrency rejections.",
                "# TYPE docustruct_concurrency_rejections_total counter",
                f"docustruct_concurrency_rejections_total {self._concurrency_rejections}",
                "# HELP docustruct_model_retries_total Total retry attempts caused by transient upstream LLM failures.",
                "# TYPE docustruct_model_retries_total counter",
                f"docustruct_model_retries_total {self._model_retries}",
            ])

            # Peticiones HTTP
            lines.extend([
                "# HELP docustruct_http_requests_total Total HTTP requests handled.",
                "# TYPE docustruct_http_requests_total counter",
            ])
            for (method, endpoint, status_code), count in sorted(self._http_requests.items()):
                lines.append(
                    f'docustruct_http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {count}'
                )

            # Histograma de Duración HTTP
            lines.extend([
                "# HELP docustruct_http_request_duration_seconds HTTP request latency distribution.",
                "# TYPE docustruct_http_request_duration_seconds histogram",
            ])
            cumulative = 0
            for bucket in LATENCY_BUCKETS:
                cumulative += self._duration_buckets[bucket]
                lines.append(f'docustruct_http_request_duration_seconds_bucket{{le="{bucket}"}} {cumulative}')
            lines.append(f'docustruct_http_request_duration_seconds_bucket{{le="+Inf"}} {self._duration_count}')
            lines.append(f"docustruct_http_request_duration_seconds_sum {round(self._duration_sum, 6)}")
            lines.append(f"docustruct_http_request_duration_seconds_count {self._duration_count}")

        lines.append("")  # Salto de línea final exigido por especificación Prometheus
        return "\n".join(lines)


# Singleton de telemetría global
telemetry_registry = InMemoryMetricsRegistry()
