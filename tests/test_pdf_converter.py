"""Unit tests for PDF rasterization and image utilities."""

import io
import os

import pypdfium2 as pdfium
import pytest
from PIL import Image

from src.services.pdf_converter import (
    CorruptPDFError,
    ExceededPageLimitError,
    PDFConverterService,
)
from src.utils.image_utils import (
    base64_data_uri_to_pil,
    optimize_image_for_vision,
    pil_to_base64_data_uri,
)


def create_synthetic_pdf(num_pages: int = 2) -> bytes:
    """Helper que crea un PDF sintético de N páginas en memoria para pruebas."""
    doc = pdfium.PdfDocument.new()
    for _ in range(num_pages):
        # Página tamaño estándar A4: 595 x 842 puntos
        doc.new_page(595, 842)
    buffer = io.BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


# =====================================================================
# Pruebas de Image Utils
# =====================================================================


def test_pil_to_base64_and_back():
    """Valida la serialización de imagen PIL a Base64 URI y su decodificación inversa."""
    img = Image.new("RGB", (200, 100), color="blue")
    uri = pil_to_base64_data_uri(img, image_format="JPEG")

    assert uri.startswith("data:image/jpeg;base64,")

    recovered = base64_data_uri_to_pil(uri)
    assert recovered.size == (200, 100)


def test_optimize_image_resizes_large_images():
    """Valida que imágenes superiores a max_dimension se redimensionen proporcionalmente."""
    large_img = Image.new("RGB", (4000, 2000), color="red")
    optimized = optimize_image_for_vision(large_img, max_dimension=2048)

    assert optimized.width == 2048
    assert optimized.height == 1024


def test_optimize_image_handles_rgba_alpha():
    """Valida que imágenes con canal Alpha (RGBA) se conviertan a RGB con fondo blanco."""
    rgba_img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    optimized = optimize_image_for_vision(rgba_img)

    assert optimized.mode == "RGB"


# =====================================================================
# Pruebas de PDF Converter Service
# =====================================================================


def test_convert_synthetic_pdf_success():
    """Valida la conversión de un PDF sintético de 3 páginas a 150 DPI."""
    pdf_bytes = create_synthetic_pdf(num_pages=3)
    service = PDFConverterService(dpi=150, max_pages=10)

    rendered_doc = service.convert(pdf_bytes)

    assert rendered_doc.total_pages == 3
    assert rendered_doc.dpi == 150
    assert len(rendered_doc.pages) == 3

    # A4 a 150 DPI: 595 * (150/72) = ~1240 px, 842 * (150/72) = ~1754 px
    first_page = rendered_doc.pages[0]
    assert first_page.page_number == 1
    assert 1238 <= first_page.width_px <= 1242
    assert 1752 <= first_page.height_px <= 1756
    assert first_page.image_base64_uri.startswith("data:image/jpeg;base64,")


def test_convert_corrupt_pdf_fails_fast():
    """Valida que bytes corruptos o texto plano disparen CorruptPDFError."""
    service = PDFConverterService()
    corrupt_bytes = b"Este no es un archivo PDF valido"

    with pytest.raises(CorruptPDFError):
        service.convert(corrupt_bytes)


def test_convert_exceeds_max_pages_fails_fast():
    """Valida el rechazo temprano si el documento supera el límite configurado."""
    pdf_bytes = create_synthetic_pdf(num_pages=6)
    # Límite configurado a 5 páginas
    service = PDFConverterService(max_pages=5)

    with pytest.raises(ExceededPageLimitError) as exc_info:
        service.convert(pdf_bytes)

    assert "superando el límite máximo permitido de 5" in str(exc_info.value)


def test_convert_real_generated_sample_pdf():
    """Valida la rasterización del PDF de prueba generado documento_prueba_heterogeneo.pdf."""
    sample_path = "documento_prueba_heterogeneo.pdf"
    assert os.path.exists(sample_path)

    with open(sample_path, "rb") as f:
        pdf_bytes = f.read()

    service = PDFConverterService(dpi=150)
    rendered_doc = service.convert(pdf_bytes)

    assert rendered_doc.total_pages == 4
    for p in rendered_doc.pages:
        assert p.width_px > 1200
        assert p.height_px > 1700
        assert p.image_base64_uri.startswith("data:image/jpeg;base64,")
