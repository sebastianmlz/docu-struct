"""Comprehensive standalone security and hardening tests for local and VPS environments."""

import io

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.security import (
    InMemoryRateLimiter,
    InvalidPDFMagicBytesError,
    ServerCapacityExceededError,
    rate_limiter,
    sanitize_filename,
    validate_pdf_magic_bytes,
)
from src.main import app
from src.services.pdf_converter import PageDimensionExceededError, PDFConverterService

client = TestClient(app)


def create_minimal_valid_pdf_bytes() -> bytes:
    """Crea bytes de un PDF mínimo legítimo que inicia con %PDF-."""
    doc = pdfium.PdfDocument.new()
    doc.new_page(595, 842)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# =====================================================================
# 1. Pruebas de Validación de Magic Bytes y Archivos Fraudulentos
# =====================================================================


def test_magic_bytes_valid_pdf():
    """Valida que un PDF auténtico sea aceptado por el validador binario."""
    valid_bytes = create_minimal_valid_pdf_bytes()
    assert valid_bytes.startswith(b"%PDF-")
    # No debe levantar excepción
    validate_pdf_magic_bytes(valid_bytes)


def test_magic_bytes_rejects_html_and_text():
    """Valida que archivos de texto plano o HTML disfrazados como PDF sean rechazados."""
    fake_html = b"<!DOCTYPE html><html><head><title>Phishing</title></head></html>"
    with pytest.raises(InvalidPDFMagicBytesError) as exc_info:
        validate_pdf_magic_bytes(fake_html)
    assert "no contiene la firma binaria requerida" in str(exc_info.value)

    fake_text = b"Nombre,Sueldo,Cargo\nJuan,1000,Analista"
    with pytest.raises(InvalidPDFMagicBytesError):
        validate_pdf_magic_bytes(fake_text)


def test_magic_bytes_rejects_executables():
    """Valida que archivos ejecutables PE/ELF disfrazados sean bloqueados."""
    fake_pe = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 50
    with pytest.raises(InvalidPDFMagicBytesError):
        validate_pdf_magic_bytes(fake_pe)


def test_process_endpoint_rejects_fake_pdf_magic_bytes():
    """Valida que el endpoint /process rechace con HTTP 400 un archivo con extensión .pdf pero contenido fraudulento."""
    fake_payload = b"<html><script>alert(1)</script></html>"
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("malware.pdf", fake_payload, "application/pdf")},
    )
    assert response.status_code == 400
    assert "firma binaria requerida" in response.json()["detail"]


# =====================================================================
# 2. Pruebas de Sanitización Forense de Nombres de Archivo
# =====================================================================


def test_sanitize_filename_path_traversal():
    """Valida que rutas relativas o absolutas de escape sean reducidas al nombre base."""
    assert sanitize_filename("../../../../etc/shadow.pdf") == "shadow.pdf"
    assert sanitize_filename("..\\..\\Windows\\System32\\cmd.exe.pdf") == "cmd.exe.pdf"
    assert sanitize_filename("/var/log/nginx/access.pdf") == "access.pdf"


def test_sanitize_filename_control_characters():
    """Valida que caracteres de control y secuencias peligrosas sean reemplazadas."""
    malicious = "factura\x00\x08_confidencial\r\n.pdf"
    clean = sanitize_filename(malicious)
    assert "\x00" not in clean
    assert "\r" not in clean
    assert clean.endswith(".pdf")


def test_sanitize_filename_missing_extension():
    """Valida el manejo de nombres vacíos o sin caracteres."""
    assert sanitize_filename("reporte_sin_extension") == "reporte_sin_extension"
    assert sanitize_filename("") == "document.pdf"
    assert sanitize_filename(None) == "document.pdf"


# =====================================================================
# 3. Pruebas de Rate Limiting Autónomo (Sliding Window en Memoria)
# =====================================================================


def test_in_memory_rate_limiter_logic():
    """Valida la lógica del limitador deslizante thread-safe."""
    limiter = InMemoryRateLimiter()
    test_ip = "192.0.2.45"

    # Permitir hasta 3 peticiones en la ventana
    for _ in range(3):
        allowed, retry_after = limiter.is_allowed(test_ip, max_requests=3, window_seconds=10)
        assert allowed is True
        assert retry_after == 0

    # La 4ª petición debe ser rechazada con tiempo de espera positivo
    allowed, retry_after = limiter.is_allowed(test_ip, max_requests=3, window_seconds=10)
    assert allowed is False
    assert retry_after > 0


def test_process_endpoint_rate_limiting_enforced():
    """Valida que enviar ráfagas por encima del límite retorne HTTP 429 Too Many Requests con Retry-After."""
    test_ip = "198.51.100.99"
    headers = {"X-Forwarded-For": test_ip}
    fake_pdf = b"%PDF-1.4 dummy valid header content"

    limit = settings.RATE_LIMIT_PROCESS_PER_MINUTE
    # Consumir el cupo asignado para esta IP
    for _ in range(limit):
        rate_limiter.is_allowed(test_ip, max_requests=limit, window_seconds=60)

    # La siguiente petición a la API con esa IP debe rebotar con 429
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("doc.pdf", fake_pdf, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 429
    assert "Límite de procesamiento excedido" in response.json()["detail"]
    assert "Retry-After" in response.headers


# =====================================================================
# 4. Pruebas de Concurrencia y Blindaje contra OOM (ConcurrencyGuard)
# =====================================================================


@pytest.mark.asyncio
async def test_concurrency_guard_saturation():
    """Valida que si se agotan las ranuras del semáforo se lance ServerCapacityExceededError."""
    # Crear un guardián temporal con 1 sola ranura
    from src.core.security import ConcurrencyGuard
    strict_guard = ConcurrencyGuard(max_slots=1)

    async with strict_guard.acquire_slot():
        assert strict_guard.active_jobs == 1
        # El segundo intento simultáneo debe ser rechazado inmediatamente
        with pytest.raises(ServerCapacityExceededError) as exc_info:
            async with strict_guard.acquire_slot():
                pass
        assert "capacidad máxima simultánea" in str(exc_info.value)

    # Una vez liberado, debe permitir una nueva ranura
    assert strict_guard.active_jobs == 0
    async with strict_guard.acquire_slot():
        assert strict_guard.active_jobs == 1


# =====================================================================
# 5. Pruebas de Detección de Bombas de Píxeles (Pixel Bombs)
# =====================================================================


def test_pixel_bomb_dimension_rejection():
    """Valida que páginas con dimensiones descomunales sean abortadas antes de agotar memoria."""
    # Crear un PDF con dimensiones gigantescas (8000 x 8000 puntos)
    doc = pdfium.PdfDocument.new()
    doc.new_page(8000, 8000)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    giant_pdf_bytes = buf.getvalue()

    service = PDFConverterService()
    with pytest.raises(PageDimensionExceededError) as exc_info:
        service.convert(giant_pdf_bytes)

    assert "excede las dimensiones máximas permitidas" in str(exc_info.value)


# =====================================================================
# 6. Pruebas de Cabeceras Avanzadas de Seguridad y CSP
# =====================================================================


def test_advanced_security_headers_and_csp():
    """Valida la presencia de cabeceras CSP, COOP, CORP y Cross-Domain."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    headers = response.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-Permitted-Cross-Domain-Policies") == "none"
    assert headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert headers.get("Cross-Origin-Resource-Policy") == "same-origin"

    csp = headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "cdn.tailwindcss.com" in csp
