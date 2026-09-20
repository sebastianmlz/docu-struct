"""Unit tests for the in-memory idempotent LRU document cache."""

from concurrent.futures import ThreadPoolExecutor

from src.core.cache import IdempotentDocumentCache


def test_cache_insert_and_retrieve_hit():
    """Valida inserción, cálculo de clave determinista y acierto de caché (HIT)."""
    cache = IdempotentDocumentCache(max_entries=10, ttl_seconds=60)
    pdf_sample = b"%PDF-1.4 test document content"

    key = cache.compute_cache_key(pdf_sample, "gemini-3.8-flash", 150)
    assert cache.get(key) is None
    assert cache.stats["misses"] == 1
    assert cache.stats["hits"] == 0

    mock_result = {"status": "success", "tables": 2}
    cache.set(key, mock_result)

    retrieved = cache.get(key)
    assert retrieved == mock_result
    assert cache.stats["hits"] == 1
    assert cache.stats["size"] == 1


def test_cache_lru_eviction():
    """Valida que se desaloje el elemento más antiguo cuando se supera max_entries."""
    cache = IdempotentDocumentCache(max_entries=3, ttl_seconds=300)

    # Insertar 3 elementos (A, B, C)
    cache.set("key_A", "doc_A")
    cache.set("key_B", "doc_B")
    cache.set("key_C", "doc_C")
    assert cache.stats["size"] == 3

    # Acceder a A para que B sea el menos recientemente usado (LRU)
    assert cache.get("key_A") == "doc_A"

    # Insertar un 4to elemento (D). Debe desalojar B.
    cache.set("key_D", "doc_D")
    assert cache.stats["size"] == 3
    assert cache.stats["evictions"] == 1

    # B debe haber sido desalojado
    assert cache.get("key_B") is None
    # A, C y D deben seguir presentes
    assert cache.get("key_A") == "doc_A"
    assert cache.get("key_C") == "doc_C"
    assert cache.get("key_D") == "doc_D"


def test_cache_ttl_expiration():
    """Valida que entradas con TTL expirado sean descartadas automáticamente."""
    cache = IdempotentDocumentCache(max_entries=5, ttl_seconds=1)
    cache.set("key_exp", "expiring_doc")

    assert cache.get("key_exp") == "expiring_doc"

    # Simular paso del tiempo manipulando la marca de inserción
    inserted_at, data = cache._cache["key_exp"]
    cache._cache["key_exp"] = (inserted_at - 10.0, data)

    # Debe retornar None y contar como expulsión
    assert cache.get("key_exp") is None
    assert cache.stats["evictions"] == 1
    assert cache.stats["size"] == 0


def test_cache_disabled_behavior():
    """Valida que si cache.enabled es False no guarde ni devuelva entradas."""
    cache = IdempotentDocumentCache(max_entries=5, ttl_seconds=60, enabled=False)
    cache.set("key_dis", "data")
    assert cache.get("key_dis") is None
    assert cache.stats["size"] == 0


def test_cache_concurrent_thread_safety():
    """Valida la consistencia de la caché bajo lecturas y escrituras concurrentes."""
    cache = IdempotentDocumentCache(max_entries=20, ttl_seconds=300)

    def worker(worker_id: int):
        for i in range(25):
            k = f"key_{worker_id}_{i % 5}"
            cache.set(k, f"val_{worker_id}_{i}")
            _ = cache.get(k)

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker, idx) for idx in range(6)]
        for f in futures:
            f.result()

    assert cache.stats["size"] <= 20
    assert cache.stats["hits"] > 0
