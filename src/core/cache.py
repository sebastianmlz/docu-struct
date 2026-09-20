"""In-memory idempotent document cache for DocuStruct.

Provides deterministic SHA-256 keyed caching with strict LRU eviction and TTL expiry,
preventing duplicate vision API invocations and preserving upstream quota.
Operates 100% in memory with zero external dependencies.
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Any

from src.core.config import settings

logger = logging.getLogger("docustruct.core.cache")


class IdempotentDocumentCache:
    """Thread-safe LRU cache with TTL for extracted document representations."""

    def __init__(self, max_entries: int = 50, ttl_seconds: int = 3600, enabled: bool = True) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    @staticmethod
    def compute_cache_key(pdf_bytes: bytes, model_name: str, dpi: int) -> str:
        """Calcula una clave determinista basada en el hash SHA-256 del binario y la configuración."""
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        clean_model = model_name.strip().lower()
        return f"{pdf_sha256}:{clean_model}:{dpi}"

    def get(self, key: str) -> Any | None:
        """Recupera un resultado de caché si existe y no ha expirado su TTL."""
        if not self.enabled:
            return None

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            inserted_at, data = self._cache[key]
            # Verificar expiración por TTL
            if (time.time() - inserted_at) > self.ttl_seconds:
                del self._cache[key]
                self._misses += 1
                self._evictions += 1
                logger.debug("Entrada de caché expirada por TTL para clave %s", key[:16])
                return None

            # Mover al final para política Least-Recently-Used (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            logger.info("Acierto de caché (HIT) para clave %s... (Total hits: %d)", key[:16], self._hits)
            return data

    def set(self, key: str, value: Any) -> None:
        """Guarda un resultado en la caché con política de desalojo LRU si se alcanza la capacidad máxima."""
        if not self.enabled:
            return

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.max_entries:
                # Desalojar el elemento menos recientemente usado (primero en OrderedDict)
                evicted_key, _ = self._cache.popitem(last=False)
                self._evictions += 1
                logger.debug("Capacidad máxima de caché alcanzada. Desalojado LRU: %s", evicted_key[:16])

            self._cache[key] = (time.time(), value)
            logger.debug("Documento indexado en caché con clave %s... (Tamaño actual: %d)", key[:16], len(self._cache))

    def clear(self) -> None:
        """Vacía completamente la caché y reinicia los contadores."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    @property
    def stats(self) -> dict[str, Any]:
        """Retorna estadísticas operativas de la caché."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "size": len(self._cache),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_ratio": (
                    round(self._hits / (self._hits + self._misses), 3)
                    if (self._hits + self._misses) > 0
                    else 0.0
                ),
            }


# Instancia singleton para uso en todo el microservicio
document_cache = IdempotentDocumentCache(
    max_entries=settings.CACHE_MAX_ENTRIES,
    ttl_seconds=settings.CACHE_TTL_SECONDS,
    enabled=settings.CACHE_ENABLED,
)
