"""API Response envelopes and schemas for DocuStruct endpoints."""

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from src.schemas.document import DocumentExtractionResult

T = TypeVar("T")


class ProcessingStatus(str, Enum):
    """Estado de finalización del procesamiento."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ProcessingMetrics(BaseModel):
    """Métricas de rendimiento y observabilidad del pipeline de extracción."""

    total_pages_processed: int = Field(
        ge=0, description="Número de páginas rasterizadas e inferidas."
    )
    duration_seconds: float = Field(
        ge=0.0, description="Tiempo total de procesamiento en segundos."
    )
    llm_model_used: str = Field(
        description="Identificador del modelo multimodal utilizado (e.g. 'gpt-4o')."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Marca temporal UTC de finalización del proceso.",
    )


class ApiResponse(BaseModel, Generic[T]):
    """Envelope genérico para respuestas estándar de la API."""

    status: ProcessingStatus
    message: str
    data: T | None = None
    errors: list[str] = Field(default_factory=list)


class DocumentProcessResponse(ApiResponse[DocumentExtractionResult]):
    """Respuesta específica para el endpoint de análisis de documentos."""

    metrics: ProcessingMetrics | None = None
