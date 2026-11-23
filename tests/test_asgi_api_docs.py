"""/docs y /openapi.json no se publican en producción salvo opt-in explícito
(auditoría 23-nov, H9.5)."""
import pytest
from fastapi.testclient import TestClient

import asgi


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_desactivados_por_defecto(path):
    assert TestClient(asgi.app).get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_docs_con_opt_in(path):
    app = asgi.create_app(expose_api_docs=True)
    assert TestClient(app).get(path).status_code == 200


def test_variable_de_entorno(monkeypatch):
    from src import config
    monkeypatch.setenv("MNEMO_EXPOSE_API_DOCS", "true")
    assert config.api_docs_exposed() is True
    monkeypatch.setenv("MNEMO_EXPOSE_API_DOCS", "")
    assert config.api_docs_exposed() is False
