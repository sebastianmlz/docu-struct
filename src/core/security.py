"""Security, rate limiting, and resource protection primitives for DocuStruct.

Operates autonomously in-memory without external dependencies (no Redis required),
providing strict file validation, IP rate limiting, and concurrency limits for VPS environments.
"""

import asyncio
import logging
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import Request

from src.core.config import settings

logger = logging.getLogger("docustruct.core.security")


# =====================================================================
# Excepciones de Dominio de Seguridad
# =====================================================================


class SecurityValidationError(Exception):
    """Excepción base para fallos en las validaciones de seguridad."""


class InvalidPDFMagicBytesError(SecurityValidationError):
    """Lanzada cuando el contenido del archivo no inicia con la firma binaria de PDF."""


class ServerCapacityExceededError(SecurityValidationError):
    """Lanzada cuando se supera el límite de concurrencia de procesamiento en memoria."""


# =====================================================================
# Validación de Archivos y Sanitización Forense
# =====================================================================


def validate_pdf_magic_bytes(pdf_bytes: bytes) -> None:
    """Valida la firma mágica del archivo para garantizar que es un PDF legítimo.

    Según la especificación ISO 32000-1 (Sección 7.5.2), el encabezado debe contener
    los 5 caracteres '%PDF-' en las primeras líneas del archivo.
    """
    if not pdf_bytes or len(pdf_bytes) < 5:
        raise InvalidPDFMagicBytesError("El archivo está vacío o es demasiado pequeño para ser un PDF válido.")

    # Busca la firma mágica en los primeros 1024 bytes (tolerancia para comentarios de cabecera)
    header_chunk = pdf_bytes[:1024]
    if b"%PDF-" not in header_chunk:
        raise InvalidPDFMagicBytesError(
            "El archivo cargado no contiene la firma binaria requerida (%PDF-). "
            "Posible archivo ejecutable, HTML o script malicioso camuflado."
        )


def sanitize_filename(raw_filename: str | None) -> str:
    """Sanitiza el nombre del archivo para neutralizar ataques de Path Traversal e Inyecciones.

    Extrae únicamente el nombre base (sin directorios ni rutas relativas),
    remueve caracteres de control y normaliza a caracteres seguros.
    """
    if not raw_filename or not raw_filename.strip():
        return "document.pdf"

    # 1. Extraer nombre base descartando rutas Unix y Windows (../, ..\)
    base_name = Path(raw_filename).name

    # 2. Filtrar caracteres no seguros (mantener alfanuméricos, guiones, puntos y guiones bajos)
    clean_name = re.sub(r"[^\w\.\-\s]", "_", base_name, flags=re.ASCII)
    clean_name = re.sub(r"\s+", "_", clean_name).strip("._")

    # 3. Limitar longitud máxima
    if len(clean_name) > 120:
        clean_name = clean_name[:120]

    return clean_name or "document.pdf"


def get_client_ip(request: Request) -> str:
    """Obtiene la IP del cliente con soporte para cabeceras X-Forwarded-For (útil tras Nginx/Cloudflare en VPS)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Tomar la primera IP de la cadena (la del cliente original)
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


# =====================================================================
# Rate Limiting Autónomo en Memoria (Sliding Window)
# =====================================================================


class InMemoryRateLimiter:
    """Limitador de tasa de peticiones deslizante (Sliding Window) thread-safe en memoria.

    No requiere Redis y es ideal para instancias VPS individuales.
    Realiza limpieza periódica de registros inactivos para prevenir fugas de memoria.
    """

    def __init__(self, cleanup_interval_seconds: int = 300) -> None:
        self._lock = threading.Lock()
        self._requests: dict[str, list[float]] = {}
        self._cleanup_interval = cleanup_interval_seconds
        self._last_cleanup = time.monotonic()

    def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> tuple[bool, int]:
        """Comprueba si la clave (IP) tiene permitido realizar una nueva petición.

        Retorna una tupla (permitido: bool, retry_after_segundos: int).
        """
        now = time.monotonic()

        with self._lock:
            self._maybe_cleanup(now)

            timestamps = self._requests.get(key, [])
            # Filtrar marcas de tiempo fuera de la ventana deslizante
            valid_timestamps = [t for t in timestamps if now - t < window_seconds]

            if len(valid_timestamps) >= max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(1, int(window_seconds - (now - oldest)))
                self._requests[key] = valid_timestamps
                return False, retry_after

            # Registrar la petición actual
            valid_timestamps.append(now)
            self._requests[key] = valid_timestamps
            return True, 0

    def _maybe_cleanup(self, now: float) -> None:
        """Purga entradas de IPs inactivas para mantener un tamaño de memoria acotado."""
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        expired_keys = []
        for key, timestamps in self._requests.items():
            if not timestamps or (now - timestamps[-1] > 300):
                expired_keys.append(key)

        for key in expired_keys:
            self._requests.pop(key, None)


# Instancia singleton del limitador en memoria
rate_limiter = InMemoryRateLimiter()


# =====================================================================
# Control de Concurrencia en Memoria (Blindaje Anti-OOM)
# =====================================================================


class ConcurrencyGuard:
    """Guardián de concurrencia basado en asyncio.Semaphore para proteger la memoria RAM del VPS.

    Garantiza que no se procesen más documentos simultáneos de los permitidos por MAX_CONCURRENT_JOBS.
    """

    def __init__(self, max_slots: int | None = None) -> None:
        self._max_slots = max_slots or settings.MAX_CONCURRENT_JOBS
        self._semaphore: asyncio.Semaphore | None = None
        self._active_count = 0
        self._lock = asyncio.Lock()

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_slots)
        return self._semaphore

    @asynccontextmanager
    async def acquire_slot(self) -> AsyncIterator[None]:
        """Adquiere una ranura de procesamiento de forma no bloqueante o con rechazo inmediato si está saturado."""
        sem = self._get_semaphore()

        # Intentar adquirir inmediatamente la ranura de memoria
        if sem.locked():
            logger.warning(
                "Capacidad máxima de procesamiento alcanzada (%d ranuras ocupadas). Aplicando backpressure.",
                self._max_slots,
            )
            raise ServerCapacityExceededError(
                f"El servidor ha alcanzado su capacidad máxima simultánea ({self._max_slots} documentos). "
                "Por favor intenta nuevamente en unos segundos para evitar saturación de memoria."
            )

        await sem.acquire()
        async with self._lock:
            self._active_count += 1
            logger.info("Ranura de procesamiento adquirida. Trabajos activos: %d/%d", self._active_count, self._max_slots)

        try:
            yield
        finally:
            sem.release()
            async with self._lock:
                self._active_count = max(0, self._active_count - 1)
                logger.info("Ranura de procesamiento liberada. Trabajos activos: %d/%d", self._active_count, self._max_slots)

    @property
    def active_jobs(self) -> int:
        return self._active_count


# Instancia singleton del guardián de concurrencia
concurrency_guard = ConcurrencyGuard()
