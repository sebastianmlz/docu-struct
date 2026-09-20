"""Integration tests for FastAPI endpoints and document processing API."""

import io
from unittest.mock import patch

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.main import app
from src.schemas.document import (
    BlockType,
    DocumentBlock,
    HeaderMetadataPayload,
    IdentityCredentialPayload,
    PageExtraction,
    TablePayload,
    TableSplitMetadata,
)

client = TestClient(app)


def create_synthetic_pdf(num_pages: int = 1) -> bytes:
    """Helper que crea un PDF sintético de N páginas en memoria para pruebas."""
    doc = pdfium.PdfDocument.new()
    for _ in range(num_pages):
        doc.new_page(595, 842)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_health_check_endpoint():
    """Valida el endpoint GET /api/v1/health."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "active_model" in data


def test_web_home_endpoint():
    """Valida que el endpoint GET / sirva la página Jinja2 con Tailwind."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DocuStruct" in response.text


def test_process_invalid_file_extension():
    """Valida que subir un archivo que no sea .pdf retorne HTTP 400."""
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("documento.txt", b"Texto plano", "text/plain")},
    )
    assert response.status_code == 400
    assert "Se requiere un archivo PDF (.pdf)" in response.json()["detail"]


def test_process_corrupt_pdf_file():
    """Valida que un PDF corrupto sea rechazado con HTTP 400 Fail-Fast."""
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("corrupto.pdf", b"PDF Falso que no tiene cabecera ni nada", "application/pdf")},
    )
    assert response.status_code == 400
    assert "no es un PDF válido o está dañado" in response.json()["detail"]


def test_process_exceeds_max_pages_limit():
    """Valida el rechazo de documentos que superan el límite de páginas."""
    pdf_bytes = create_synthetic_pdf(num_pages=6)

    with patch("src.core.config.settings.MAX_PAGES_PER_DOCUMENT", 5):
        response = client.post(
            "/api/v1/documents/process",
            files={"file": ("largo.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 400
        assert "superando el límite máximo permitido de 5" in response.json()["detail"]


@pytest.mark.asyncio
async def test_process_valid_pdf_end_to_end_mocked():
    """Valida el flujo completo de POST /api/v1/documents/process con inferencia mockeada."""
    pdf_bytes = create_synthetic_pdf(num_pages=2)

    mock_page_1 = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(
                reading_order_index=1,
                block_type=BlockType.HEADER_METADATA,
                header_data=HeaderMetadataPayload(document_title="Acta Notarial"),
            ),
            DocumentBlock(
                reading_order_index=2,
                block_type=BlockType.TABLE,
                table_data=TablePayload(
                    headers=["Nro", "Descripción"],
                    rows=[["1", "Item A"]],
                    split_metadata=TableSplitMetadata(
                        table_id="tab_1",
                        has_subsequent_continuation=True,
                    ),
                ),
            ),
        ],
    )

    mock_page_2 = PageExtraction(
        page_number=2,
        blocks=[
            DocumentBlock(
                reading_order_index=1,
                block_type=BlockType.TABLE,
                table_data=TablePayload(
                    headers=["Nro", "Descripción"],
                    rows=[["2", "Item B"]],
                    split_metadata=TableSplitMetadata(
                        table_id="tab_1_cont",
                        is_continuation=True,
                        continuation_of_id="tab_1",
                    ),
                ),
            ),
            DocumentBlock(
                reading_order_index=2,
                block_type=BlockType.IDENTITY_CREDENTIAL,
                credential_data=IdentityCredentialPayload(
                    full_name="Sebastián González",
                    id_number="18.999.888-K",
                ),
            ),
        ],
    )

    with patch("src.services.vision_extractor.VisionExtractorService.aextract_page") as mock_extract:
        mock_extract.side_effect = [mock_page_1, mock_page_2]

        response = client.post(
            "/api/v1/documents/process",
            files={"file": ("acta_notarial.pdf", pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["metrics"]["total_pages_processed"] == 2
        assert data["metrics"]["duration_seconds"] >= 0.0

        # Validar postprocesamiento en el resultado final
        doc_data = data["data"]
        assert doc_data["filename"] == "acta_notarial.pdf"
        assert doc_data["global_metadata"]["document_title"] == "Acta Notarial"
        assert len(doc_data["extracted_credentials"]) == 1
        assert doc_data["extracted_credentials"][0]["full_name"] == "Sebastián González"

        # Validar que la tabla fue unificada entre las 2 páginas
        assert len(doc_data["unified_tables"]) == 1
        assert len(doc_data["unified_tables"][0]["rows"]) == 2


def test_process_empty_file_fails():
    """Valida que un archivo sin contenido binario arroje HTTP 400."""
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("vacio.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "vacío o contiene bytes insuficientes" in response.json()["detail"]


def test_process_payload_too_large_fails():
    """Valida que un archivo que excede el límite de MB configurado retorne HTTP 413."""
    with patch("src.core.config.settings.MAX_UPLOAD_SIZE_MB", 1):
        huge_bytes = b"0" * (2 * 1024 * 1024)  # 2 MB cuando el límite simulado es 1 MB
        response = client.post(
            "/api/v1/documents/process",
            files={"file": ("pesado.pdf", huge_bytes, "application/pdf")},
        )
        assert response.status_code == 413
        assert "excede el tamaño máximo permitido" in response.json()["detail"]


def test_process_missing_credentials_returns_503():
    """Valida que la falta de API Key durante la inferencia retorne HTTP 503 Service Unavailable."""
    pdf_bytes = create_synthetic_pdf(num_pages=1)
    with patch("src.core.config.settings.OPENAI_API_KEY", SecretStr("")), \
         patch("src.core.config.settings.GEMINI_API_KEY", SecretStr("")), \
         patch("src.core.config.settings.GOOGLE_API_KEY", SecretStr("")):
        response = client.post(
            "/api/v1/documents/process",
            files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 503
        assert "no está configurada" in response.json()["detail"]

