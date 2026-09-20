"""Unit tests for Pydantic v2 schemas and data contracts."""

import json

from src.schemas.api_response import (
    DocumentProcessResponse,
    ProcessingMetrics,
    ProcessingStatus,
)
from src.schemas.document import (
    CENSORED_SENTINEL,
    BlockType,
    DocumentBlock,
    DocumentExtractionResult,
    HeaderMetadataPayload,
    IdentityCredentialPayload,
    PageExtraction,
    StampSignaturePayload,
    TablePayload,
    TableSplitMetadata,
    TableSplitType,
    TextParagraphPayload,
)


def test_table_censorship_normalization():
    """Valida que celdas con palabras clave de censura se normalicen al centinela."""
    table = TablePayload(
        caption="Nómina de Pagos",
        headers=["ID", "Nombre", "Salario"],
        rows=[
            ["1", "Juan Pérez", "$1500"],
            ["2", "[censurado]", "[TACHADO]"],
            ["3", "Ana López", None],
        ],
        split_metadata=TableSplitMetadata(table_id="table_1"),
    )

    assert table.rows[1][1] == CENSORED_SENTINEL
    assert table.rows[1][2] == CENSORED_SENTINEL
    assert table.rows[2][2] is None
    assert len(table.rows) == 3


def test_table_split_metadata():
    """Valida la representación de tablas partidas multi-página."""
    split_meta = TableSplitMetadata(
        table_id="table_1_part_2",
        is_continuation=True,
        continuation_of_id="table_1",
        split_type=TableSplitType.VERTICAL_CONTINUATION,
        has_subsequent_continuation=False,
    )

    table = TablePayload(
        caption="Nómina (Continuación Página 2)",
        headers=["ID", "Nombre", "Salario"],
        rows=[["4", "Carlos Ruiz", "$1800"]],
        split_metadata=split_meta,
    )

    assert table.split_metadata.is_continuation is True
    assert table.split_metadata.continuation_of_id == "table_1"
    assert table.split_metadata.split_type == TableSplitType.VERTICAL_CONTINUATION


def test_polymorphic_page_blocks_reading_order():
    """Valida la coexistencia de bloques mixtos y el orden de lectura."""
    blocks = [
        DocumentBlock(
            reading_order_index=1,
            block_type=BlockType.HEADER_METADATA,
            header_data=HeaderMetadataPayload(
                document_title="Informe Oficial de Auditoría",
                folio_or_id="EXP-2026-99",
            ),
        ),
        DocumentBlock(
            reading_order_index=2,
            block_type=BlockType.IDENTITY_CREDENTIAL,
            credential_data=IdentityCredentialPayload(
                full_name="Sebastián González",
                id_number="18.999.888-K",
                credential_type="Cédula de Identidad",
            ),
        ),
        DocumentBlock(
            reading_order_index=3,
            block_type=BlockType.TEXT_PARAGRAPH,
            text_data=TextParagraphPayload(
                heading="1. ANTECEDENTES",
                content="El presente informe da cuenta de las operaciones realizadas...",
            ),
        ),
        DocumentBlock(
            reading_order_index=4,
            block_type=BlockType.STAMP_SIGNATURE,
            signature_data=StampSignaturePayload(
                signer_name="Carlos Valenzuela",
                signer_role_or_title="Director de Operaciones",
                has_physical_signature=True,
                has_stamp_or_seal=True,
            ),
        ),
    ]

    page = PageExtraction(
        page_number=1,
        blocks=blocks,
        page_summary="Página de inicio con carnet incrustado y antecedentes",
    )

    assert len(page.blocks) == 4
    # Validar que los índices están ordenados
    indices = [b.reading_order_index for b in page.blocks]
    assert indices == [1, 2, 3, 4]


def test_page_extraction_json_schema_compatibility():
    """Valida que el modelo PageExtraction genere un JSON Schema válido para OpenAI."""
    schema = PageExtraction.model_json_schema()
    assert "properties" in schema
    assert "blocks" in schema["properties"]
    assert "page_number" in schema["properties"]
    # Comprobar que es serializable a JSON estándar
    schema_str = json.dumps(schema)
    assert len(schema_str) > 100


def test_document_process_response_envelope():
    """Valida la serialización de la respuesta completa de la API con métricas."""
    doc_result = DocumentExtractionResult(
        document_id="doc-abc-123",
        filename="contrato_mixto.pdf",
        total_pages=1,
        pages=[],
        has_censored_content=True,
    )

    metrics = ProcessingMetrics(
        total_pages_processed=1,
        duration_seconds=3.45,
        llm_model_used="gpt-4o",
    )

    response = DocumentProcessResponse(
        status=ProcessingStatus.SUCCESS,
        message="Documento analizado con éxito.",
        data=doc_result,
        metrics=metrics,
    )

    json_dict = response.model_dump()
    assert json_dict["status"] == "success"
    assert json_dict["data"]["filename"] == "contrato_mixto.pdf"
    assert json_dict["metrics"]["duration_seconds"] == 3.45
    assert json_dict["data"]["has_censored_content"] is True
