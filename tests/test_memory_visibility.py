"""¿Repo privado? Ante la duda, público; caché corta por repo (no un GET por run)."""
from unittest.mock import MagicMock

import pytest

from src.memory import visibility


@pytest.fixture(autouse=True)
def _clean():
    visibility.clear_cache()
    yield
    visibility.clear_cache()


def _host(result=True, error=None, name="o/r"):
    host = MagicMock()
    host.repo_full_name = name
    host.repo_is_private.side_effect = error
    host.repo_is_private.return_value = result
    return host


def test_privado_y_cacheado_por_repo():
    host = _host(True)
    assert visibility.repo_is_private(host) and visibility.repo_is_private(host)
    assert host.repo_is_private.call_count == 1
    other = _host(False, name="o/otro")
    assert visibility.repo_is_private(other) is False


def test_error_es_publico_y_no_se_cachea():
    host = _host(error=RuntimeError("red"))
    assert visibility.repo_is_private(host) is False
    host.repo_is_private.side_effect = None
    assert visibility.repo_is_private(host) is True


def test_sin_metodo_es_publico():
    assert visibility.repo_is_private(object()) is False


def test_la_cache_caduca(monkeypatch):
    host = _host(True)
    clock = iter([0.0, visibility.CACHE_SECONDS + 1, visibility.CACHE_SECONDS + 1])
    monkeypatch.setattr(visibility.time, "monotonic", lambda: next(clock))
    visibility.repo_is_private(host)
    visibility.repo_is_private(host)
    assert host.repo_is_private.call_count == 2
