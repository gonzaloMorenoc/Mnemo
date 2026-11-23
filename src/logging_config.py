"""Configuración de logging del proceso (auditoría 2026-11-23 #20).

Sin configurar, el root logger de Python solo emite WARNING: los `logger.info` de la
app se perdían. Nivel por la variable de entorno LOG_LEVEL (INFO por defecto). El
formato solo lleva hora, nivel, logger y mensaje: los secretos no salen de aquí, y
el código de la app no debe pasarlos a los mensajes.
"""
import logging
import os
from typing import Optional

LOG_LEVEL_ENV = "LOG_LEVEL"
DEFAULT_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
_HANDLER_MARK = "_mnemo_handler"


def resolve_level(raw: Optional[str]) -> int:
    """Nivel numérico a partir del texto; un valor vacío o desconocido cae a INFO."""
    name = (raw or "").strip().upper() or DEFAULT_LOG_LEVEL
    level = logging.getLevelName(name)
    return level if isinstance(level, int) else logging.getLevelName(DEFAULT_LOG_LEVEL)


def configure_logging() -> None:
    """Configura el root logger una sola vez (idempotente: no duplica handlers)."""
    root = logging.getLogger()
    root.setLevel(resolve_level(os.getenv(LOG_LEVEL_ENV)))
    if any(getattr(h, _HANDLER_MARK, False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    setattr(handler, _HANDLER_MARK, True)
    root.addHandler(handler)
