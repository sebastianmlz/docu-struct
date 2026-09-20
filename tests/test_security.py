"""Security validation and hardening tests for DocuStruct."""

from fastapi.testclient import TestClient

from src.core.config import Settings
from src.main import app
from src.schemas.document import (
    BlockType,
    DocumentBlock,
    IdentityCredentialPayload,
    PageExtraction,
    TablePayload,
    TableSplitMetadata,
)
from src.services.postprocessor import DocumentPostprocessor

client = TestClient(app)


def test_security_headers_on_api_endpoints():
    """Valida que los endpoints API inyecten cabeceras defensivas estándar."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    headers = response.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in headers.get("Permissions-Policy", "")


def test_security_headers_on_web_endpoints():
    """Valida que las rutas web del SPA contengan cabeceras contra clickjacking y sniffing."""
    response = client.get("/")
    assert response.status_code == 200
    headers = response.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"


def test_cors_origins_parsing():
    """Valida que la configuración de CORS parsee orígenes múltiples correctamente."""
    cfg = Settings(CORS_ORIGINS="https://app.example.com, https://admin.example.com")
    assert cfg.cors_origins_list == ["https://app.example.com", "https://admin.example.com"]

    cfg_wildcard = Settings(CORS_ORIGINS="*")
    assert cfg_wildcard.cors_origins_list == ["*"]


def test_xss_payload_safety_in_document_pipeline():
    """Valida que payloads maliciosos de XSS en tablas y credenciales no rompan el postprocesador."""
    xss_script = "<script>alert('xss')</script>"
    xss_img = "<img src=x onerror=alert(1)>"

    page = PageExtraction(
        page_number=1,
        blocks=[
            DocumentBlock(
                block_type=BlockType.TABLE,
                reading_order_index=1,
                table_data=TablePayload(
                    headers=["ID", xss_script],
                    rows=[
                        ["1", xss_img],
                        ["2", "Dato seguro"],
                    ],
                    split_metadata=TableSplitMetadata(table_id="table_sec"),
                ),
            ),
            DocumentBlock(
                block_type=BlockType.IDENTITY_CREDENTIAL,
                reading_order_index=2,
                credential_data=IdentityCredentialPayload(
                    credential_type="RUN",
                    full_name=xss_script,
                    id_number="18.999.888-K",
                ),
            ),
        ],
    )

    processor = DocumentPostprocessor()
    result = processor.process(document_id="sec_test_01", filename="test.pdf", pages=[page])

    # Se preservan como texto crudo sin ejecución y sin corromper esquemas
    assert len(result.unified_tables) == 1
    assert result.unified_tables[0].headers[1] == xss_script
    assert result.unified_tables[0].rows[0][1] == xss_img
    assert len(result.extracted_credentials) == 1
    assert result.extracted_credentials[0].full_name == xss_script


def test_path_traversal_filename_resilience():
    """Valida que intentos de Directory Traversal en el nombre del archivo no causen fallos de seguridad."""
    malicious_filename = "../../../../etc/passwd.pdf"
    fake_content = b"%PDF-1.4 dummy content"

    response = client.post(
        "/api/v1/documents/process",
        files={"file": (malicious_filename, fake_content, "application/pdf")},
    )
    # Debe ser procesado o rechazado por formato, nunca escribir fuera ni generar 500 no controlado
    assert response.status_code in (400, 422)


def test_empty_zero_byte_pdf_upload():
    """Valida que un archivo PDF de 0 bytes sea rechazado de inmediato sin fugas de memoria."""
    response = client.post(
        "/api/v1/documents/process",
        files={"file": ("vacio.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "El archivo PDF est\xc3\xa1 vac\xc3\xado".encode().decode() in response.json()["detail"] or "vacío" in response.json()["detail"]
