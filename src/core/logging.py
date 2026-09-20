"""Centralized logging configuration and structured JSON observability for DocuStruct."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from src.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Retorna el identificador de solicitud correlacionado actual."""
    return request_id_ctx.get()


def set_request_id(req_id: str) -> None:
    """Fija el identificador de correlación para el contexto de ejecución asíncrono actual."""
    request_id_ctx.set(req_id)


class RequestIdFilter(logging.Filter):
    """Filtro de logging que inyecta automáticamente request_id en cada LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class StructuredJSONFormatter(logging.Formatter):
    """Formateador que emite eventos de log en formato JSON estructurado de una sola línea."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", get_request_id()),
            "module": record.module,
            "lineno": record.lineno,
        }

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Capturar atributos extra personalizados pasados al log
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "request_id"
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs and not k.startswith("_")}
        if extras:
            log_payload["extra"] = extras

        return json.dumps(log_payload, ensure_ascii=False)


def setup_logging() -> None:
    """Configura el formato y nivel de logging del sistema según el entorno."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())

    if settings.JSON_LOGS_ENABLED:
        handler.setFormatter(StructuredJSONFormatter())
    else:
        console_format = (
            "[%(asctime)s] [%(levelname)s] [req:%(request_id)s] [%(name)s:%(lineno)d] - %(message)s"
        )
        handler.setFormatter(logging.Formatter(console_format, datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]

    # Silenciar logs excesivamente verbosos de librerías externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("pypdfium2").setLevel(logging.WARNING)

    logger = logging.getLogger("docustruct")
    logger.info(
        "Sistema de logging inicializado. Formato JSON: %s, Nivel: %s",
        settings.JSON_LOGS_ENABLED,
        logging.getLevelName(log_level),
    )
