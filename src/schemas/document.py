"""Data contracts and schemas for document extraction using Pydantic v2.

Designed to be strictly validated, serializable, and fully compatible with
LangChain LCEL and OpenAI Structured Outputs (GPT-4o multimodal).
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

CENSORED_SENTINEL = "[DATO_CENSURADO]"


class BlockType(str, Enum):
    """Categoría semántica del bloque detectado visualmente."""

    HEADER_METADATA = "header_metadata"
    IDENTITY_CREDENTIAL = "identity_credential"
    TABLE = "table"
    TEXT_PARAGRAPH = "text_paragraph"
    STAMP_SIGNATURE = "stamp_signature"
    FOOTER_NOTE = "footer_note"


class TableSplitType(str, Enum):
    """Indica si una tabla es independiente o continúa otra estructura."""

    NONE = "none"
    VERTICAL_CONTINUATION = "vertical_continuation"  # Filas que continúan de la página o bloque anterior
    HORIZONTAL_CONTINUATION = "horizontal_continuation"  # Columnas adicionales divididas en un bloque inferior


# =====================================================================
# Payloads específicos por tipo de bloque
# =====================================================================


class HeaderMetadataPayload(BaseModel):
    """Encabezados oficiales, folios, membretes o metadatos de inicio de documento."""

    document_title: str | None = Field(
        default=None, description="Título oficial o asunto del documento."
    )
    document_date: str | None = Field(
        default=None, description="Fecha consignada en el documento (formato original o ISO)."
    )
    folio_or_id: str | None = Field(
        default=None, description="Número de folio, expediente, referencia o identificador único."
    )
    issuing_entity: str | None = Field(
        default=None, description="Organización, ministerio, juzgado o empresa emisora."
    )
    additional_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Pares clave-valor adicionales detectados en el encabezado."
    )


class IdentityCredentialPayload(BaseModel):
    """Documento de identidad o carnet incrustado visualmente en la página."""

    full_name: str | None = Field(
        default=None, description="Nombre completo de la persona acreditada."
    )
    id_number: str | None = Field(
        default=None, description="Número de RUN, DNI, Cédula o Pasaporte."
    )
    credential_type: str | None = Field(
        default=None, description="Tipo de credencial (e.g., 'Cédula de Identidad', 'Licencia', 'Credencial')."
    )
    nationality: str | None = Field(
        default=None, description="Nacionalidad consignada."
    )
    issue_date: str | None = Field(
        default=None, description="Fecha de emisión del carnet."
    )
    expiry_date: str | None = Field(
        default=None, description="Fecha de vencimiento."
    )
    is_censored: bool = Field(
        default=False, description="Verdadero si el documento presenta tachaduras o partes tapadas."
    )
    raw_ocr_text: str | None = Field(
        default=None, description="Texto íntegro detectado en la credencial."
    )


class TableSplitMetadata(BaseModel):
    """Metadatos para resolver el caso borde de tablas partidas y continuadas."""

    table_id: str = Field(
        description="Identificador único de la tabla dentro del documento (e.g. 'table_1')."
    )
    is_continuation: bool = Field(
        default=False,
        description="True si esta tabla es la continuación de una tabla de una página o bloque previo.",
    )
    continuation_of_id: str | None = Field(
        default=None,
        description="table_id de la tabla matriz de la que continúa (si is_continuation es True).",
    )
    split_type: TableSplitType = Field(
        default=TableSplitType.NONE,
        description="Tipo de partición (vertical para filas continuadas, horizontal para columnas partidas).",
    )
    has_subsequent_continuation: bool = Field(
        default=False,
        description="True si el contenido de esta tabla se corta al final y continúa en la siguiente página.",
    )


class TablePayload(BaseModel):
    """Estructura tabular extraída preservando alineación y detección de censura."""

    caption: str | None = Field(
        default=None, description="Título o descripción inmediata de la tabla."
    )
    headers: list[str] = Field(
        default_factory=list,
        description="Lista de nombres de las columnas. Si no hay encabezados, usar nombres inferidos Col_1, Col_2.",
    )
    rows: list[list[str | None]] = Field(
        default_factory=list,
        description=(
            "Matriz de filas y celdas. Valores censurados/tachados deben reportarse explícitamente "
            f"como '{CENSORED_SENTINEL}' o null, asegurando no alterar la cantidad de columnas."
        ),
    )
    split_metadata: TableSplitMetadata = Field(
        description="Metadatos de continuidad para reconstruir tablas multi-página."
    )

    @field_validator("rows")
    @classmethod
    def normalize_censored_cells(
        cls, rows: list[list[str | None]]
    ) -> list[list[str | None]]:
        """Garantiza que variaciones comunes de texto censurado adopten el centinela estándar."""
        normalized: list[list[str | None]] = []
        censor_keywords = {"[censurado]", "[tachado]", "censored", "tachado", "bloqueado", "[redacted]"}

        for row in rows:
            new_row: list[str | None] = []
            for cell in row:
                if cell is not None and cell.strip().lower() in censor_keywords:
                    new_row.append(CENSORED_SENTINEL)
                else:
                    new_row.append(cell)
            normalized.append(new_row)
        return normalized


class TextParagraphPayload(BaseModel):
    """Bloque de texto narrativo, cláusulas, considerandos o párrafos libres."""

    heading: str | None = Field(
        default=None, description="Subtítulo o rótulo del párrafo si existe (e.g. 'PRIMERO:', 'Art. 4')."
    )
    content: str = Field(
        description="Texto completo del párrafo en su orden de lectura original."
    )
    contains_censored_content: bool = Field(
        default=False, description="True si alguna palabra o segmento está tachado con marcador o papel."
    )


class StampSignaturePayload(BaseModel):
    """Bloque de autenticación: firmas manuscritas, digitales y timbres/sellos."""

    signer_name: str | None = Field(
        default=None, description="Nombre de la persona que firma (si es legible)."
    )
    signer_role_or_title: str | None = Field(
        default=None, description="Cargo, profesión o función del firmante (e.g. 'Notario Público', 'Gerente')."
    )
    has_physical_signature: bool = Field(
        default=False, description="True si se observa trazo manuscrito de firma."
    )
    has_stamp_or_seal: bool = Field(
        default=False, description="True si existe un sello de tinta o relieve visible."
    )
    stamp_text: str | None = Field(
        default=None, description="Texto transcrito del sello o timbre institucional."
    )
    is_digital_certificate: bool = Field(
        default=False, description="True si corresponde a un pie de firma electrónica avanzada / QR."
    )


class FooterNotePayload(BaseModel):
    """Notas al pie, folios inferiores o leyendas legales."""

    content: str = Field(description="Contenido de la nota al pie.")
    page_number_indicator: str | None = Field(
        default=None, description="Numeración detectada (e.g. 'Página 2 de 8')."
    )


# =====================================================================
# Bloque Polimórfico y Extracción de Página
# =====================================================================


class DocumentBlock(BaseModel):
    """Bloque atómico de información dentro de una página con orden de lectura secuencial.

    Utiliza un diseño consolidado con validador de consistencia, compatible 100%
    con el compilador de JSON Schema de OpenAI Structured Outputs.
    """

    reading_order_index: int = Field(
        ge=1,
        description="Orden secuencial de lectura visual de arriba a abajo y de izquierda a derecha (1, 2, 3...).",
    )
    block_type: BlockType = Field(
        description="Tipo discriminador del contenido de este bloque.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nivel estimado de confianza en la extracción visual del bloque (0.0 a 1.0).",
    )

    # Sub-payloads: el correspondiente al block_type debe estar poblado
    header_data: HeaderMetadataPayload | None = None
    credential_data: IdentityCredentialPayload | None = None
    table_data: TablePayload | None = None
    text_data: TextParagraphPayload | None = None
    signature_data: StampSignaturePayload | None = None
    footer_data: FooterNotePayload | None = None


class PageExtraction(BaseModel):
    """Resultado estructurado de la extracción visual de una página individual."""

    page_number: int = Field(
        ge=1, description="Número ordinal de la página procesada dentro del documento PDF."
    )
    blocks: list[DocumentBlock] = Field(
        default_factory=list,
        description="Lista de bloques visuales ordenados estrictamente por reading_order_index.",
    )
    page_summary: str | None = Field(
        default=None,
        description="Síntesis concisa del contenido y propósito de esta página.",
    )
    visual_anomalies: list[str] = Field(
        default_factory=list,
        description="Lista de anomalías visuales detectadas (e.g. 'Tachadura con plumón en tabla 1', 'Baja resolución').",
    )


# =====================================================================
# Resultado Consolidado del Documento Completo
# =====================================================================


class DocumentExtractionResult(BaseModel):
    """Resultado final estructurado y unificado del documento completo (1 a 10 páginas)."""

    document_id: str = Field(
        description="Identificador único asignado al proceso o hash del archivo."
    )
    filename: str = Field(
        description="Nombre original del archivo PDF procesado."
    )
    total_pages: int = Field(
        ge=1, description="Cantidad total de páginas procesadas."
    )
    global_metadata: HeaderMetadataPayload = Field(
        default_factory=HeaderMetadataPayload,
        description="Metadatos globales consolidados del documento.",
    )
    pages: list[PageExtraction] = Field(
        default_factory=list,
        description="Extracciones individuales organizadas por página.",
    )
    unified_tables: list[TablePayload] = Field(
        default_factory=list,
        description="Tablas completas resultantes tras la reconciliación y unión de tablas continuadas.",
    )
    extracted_credentials: list[IdentityCredentialPayload] = Field(
        default_factory=list,
        description="Colección consolidada de todas las credenciales/cédulas encontradas en el documento.",
    )
    extracted_signatures: list[StampSignaturePayload] = Field(
        default_factory=list,
        description="Colección consolidada de todas las firmas y sellos institucionales.",
    )
    has_censored_content: bool = Field(
        default=False,
        description="Indica si al menos un bloque o tabla en todo el documento presentó datos tachados.",
    )
