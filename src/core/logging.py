"""Centralized logging configuration for DocuStruct."""

import logging
import sys

from src.core.config import settings


def setup_logging() -> None:
    """Configura el formato y nivel de logging del sistema."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    logging_format = (
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s"
    )

    logging.basicConfig(
        level=log_level,
        format=logging_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    # Silenciar logs excesivamente verbosos de librerías externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("pypdfium2").setLevel(logging.WARNING)

    logger = logging.getLogger("docustruct")
    logger.info("Sistema de logging inicializado. Modo DEBUG: %s", settings.DEBUG)
