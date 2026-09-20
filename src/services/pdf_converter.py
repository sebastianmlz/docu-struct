"""PDF to Image rasterization service utilizing pypdfium2."""

import logging

import pypdfium2 as pdfium
from pydantic import BaseModel, Field

from src.core.config import settings
from src.utils.image_utils import pil_to_base64_data_uri

logger = logging.getLogger("docustruct.pdf_converter")


class PDFProcessingError(Exception):
    """Excepción base para fallos durante el procesamiento de PDFs."""


class CorruptPDFError(PDFProcessingError):
    """Lanzada cuando el archivo no es un PDF válido o está corrupto."""


class ExceededPageLimitError(PDFProcessingError):
    """Lanzada cuando el documento supera el límite de páginas permitido."""


class EmptyPDFError(PDFProcessingError):
    """Lanzada cuando el documento no contiene páginas procesables."""


class RenderedPage(BaseModel):
    """Representación en memoria de una página renderizada."""

    page_number: int = Field(ge=1, description="Número de página (1-indexed).")
    width_px: int = Field(ge=1, description="Ancho de la imagen renderizada en píxeles.")
    height_px: int = Field(ge=1, description="Alto de la imagen renderizada en píxeles.")
    image_base64_uri: str = Field(
        description="Data URI en base64 listo para inyectar en LangChain / OpenAI multimodal."
    )


class RenderedDocument(BaseModel):
    """Documento completo rasterizado en memoria."""

    total_pages: int = Field(ge=1, description="Número total de páginas renderizadas.")
    dpi: int = Field(ge=72, description="DPI utilizado para la rasterización.")
    pages: list[RenderedPage] = Field(
        default_factory=list, description="Lista de páginas renderizadas."
    )


class PDFConverterService:
    """Servicio de alto rendimiento para rasterización de PDFs a imágenes en memoria."""

    def __init__(
        self,
        dpi: int | None = None,
        max_pages: int | None = None,
    ) -> None:
        self.dpi = dpi or settings.PDF_RENDER_DPI
        self.max_pages = max_pages or settings.MAX_PAGES_PER_DOCUMENT
        # 72 puntos por pulgada es la escala estándar en PDF
        self.render_scale = self.dpi / 72.0

    def convert(self, pdf_bytes: bytes) -> RenderedDocument:
        """Rasteriza los bytes de un PDF a una colección de páginas en memoria.

        Aplica validaciones tempranas (Fail-Fast) sobre integridad y longitud del documento.
        """
        if not pdf_bytes or len(pdf_bytes) < 10:
            raise CorruptPDFError("El archivo recibido está vacío o contiene bytes insuficientes.")

        pdf_doc = None
        try:
            pdf_doc = pdfium.PdfDocument(pdf_bytes)
        except Exception as exc:
            logger.error("Error crítico al instanciar PdfDocument: %s", exc)
            raise CorruptPDFError(f"El archivo no es un PDF válido o está dañado: {exc}") from exc

        try:
            total_pages = len(pdf_doc)
            logger.info("PDF abierto correctamente. Total de páginas detectadas: %d", total_pages)

            if total_pages == 0:
                raise EmptyPDFError("El documento PDF no contiene ninguna página.")

            if total_pages > self.max_pages:
                raise ExceededPageLimitError(
                    f"El documento contiene {total_pages} páginas, superando el límite máximo permitido de {self.max_pages}."
                )

            rendered_pages: list[RenderedPage] = []

            for page_index in range(total_pages):
                page = None
                try:
                    page = pdf_doc.get_page(page_index)
                    # Rasterizar con la escala correspondiente al DPI
                    rendered_image = page.render(scale=self.render_scale).to_pil()
                    base64_uri = pil_to_base64_data_uri(rendered_image)

                    rendered_pages.append(
                        RenderedPage(
                            page_number=page_index + 1,
                            width_px=rendered_image.width,
                            height_px=rendered_image.height,
                            image_base64_uri=base64_uri,
                        )
                    )
                    logger.debug(
                        "Página %d/%d rasterizada exitosamente (%dx%d px)",
                        page_index + 1,
                        total_pages,
                        rendered_image.width,
                        rendered_image.height,
                    )
                finally:
                    if page is not None:
                        page.close()

            return RenderedDocument(
                total_pages=total_pages,
                dpi=self.dpi,
                pages=rendered_pages,
            )

        finally:
            if pdf_doc is not None:
                pdf_doc.close()
