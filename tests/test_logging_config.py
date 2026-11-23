"""Auditoría 2026-11-23 #20: no había configuración de logging y los INFO de la app
se perdían (el root logger de Python solo emite WARNING sin configurar)."""
import logging

import pytest

from src.logging_config import DEFAULT_LOG_LEVEL, LOG_FORMAT, configure_logging, resolve_level


@pytest.fixture
def root_restaurado():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


def test_nivel_por_defecto_es_info():
    assert DEFAULT_LOG_LEVEL == "INFO"
    assert resolve_level(None) == logging.INFO
    assert resolve_level("") == logging.INFO


def test_nivel_desde_variable_de_entorno():
    assert resolve_level("debug") == logging.DEBUG
    assert resolve_level(" WARNING ") == logging.WARNING


def test_nivel_invalido_cae_al_defecto():
    assert resolve_level("verboso") == logging.INFO


def test_formato_con_timestamp_nivel_y_logger():
    for campo in ("%(asctime)s", "%(levelname)s", "%(name)s", "%(message)s"):
        assert campo in LOG_FORMAT


def test_configure_logging_emite_info_de_la_app(root_restaurado, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    root_restaurado.handlers[:] = []
    configure_logging()
    assert root_restaurado.level == logging.INFO
    assert logging.getLogger("src.api_v2").isEnabledFor(logging.INFO)
    assert len(root_restaurado.handlers) == 1


def test_configure_logging_es_idempotente(root_restaurado):
    root_restaurado.handlers[:] = []
    configure_logging()
    configure_logging()
    assert len(root_restaurado.handlers) == 1


def test_asgi_configura_logging_al_arrancar():
    import asgi
    assert asgi.configure_logging is configure_logging
