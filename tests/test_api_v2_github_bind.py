"""Vinculación de GitHub con prueba de posesión en multi-tenant (auditoría 23-nov, H4)."""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.ci.github_auth import GitHubAuthError
from src.ci.github_install_proof import sign_install_state
from src.security import AuthenticatedUser

SECRET = "state-secret-" * 3


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _gh_auth(account="acme"):
    auth = MagicMock()
    auth.installation_account.return_value = account
    return auth


def _verifier(has=True, configured=True, error=None):
    v = MagicMock()
    v.configured = configured
    if error is not None:
        v.user_has_installation.side_effect = error
    else:
        v.user_has_installation.return_value = has
    return v


@pytest.fixture(autouse=True)
def _multitenant(monkeypatch):
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: True)
    monkeypatch.setenv("GITHUB_STATE_SECRET", SECRET)


def _client(integrations, verifier, gh_auth=None):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_integrations_repo] = lambda: integrations
    app.dependency_overrides[api_v2.get_github_app_auth] = lambda: gh_auth or _gh_auth()
    app.dependency_overrides[api_v2.get_github_user_verifier] = lambda: verifier
    return TestClient(app)


def _body(**extra):
    return {"org_id": "o1", "installation_id": "42", "repo_full_name": "acme/web", **extra}


def _state(org="o1", user="user-1"):
    return sign_install_state(org, user)


def test_con_prueba_de_posesion_vincula():
    integ, ver = MagicMock(), _verifier(has=True)
    r = _client(integ, ver).post("/v2/integrations/github",
                                 json=_body(state=_state(), code="c0de"))
    assert r.status_code == 200
    ver.user_has_installation.assert_called_once_with(code="c0de", installation_id="42")
    integ.upsert_github_config.assert_called_once()


def test_sin_prueba_400():
    integ = MagicMock()
    r = _client(integ, _verifier()).post("/v2/integrations/github", json=_body())
    assert r.status_code == 400 and "install-url" in r.json()["detail"]
    integ.upsert_github_config.assert_not_called()


@pytest.mark.parametrize("state", [
    lambda: sign_install_state("otra-org", "user-1"),
    lambda: sign_install_state("o1", "otro-usuario"),
    lambda: "basura.firma",
])
def test_state_invalido_403(state):
    integ, ver = MagicMock(), _verifier()
    r = _client(integ, ver).post("/v2/integrations/github",
                                 json=_body(state=state(), code="c"))
    assert r.status_code == 403
    ver.user_has_installation.assert_not_called()
    integ.upsert_github_config.assert_not_called()


def test_usuario_sin_acceso_a_la_instalacion_403_y_sin_oraculo_409():
    """Quien no demuestra acceso no llega al upsert: ni se queda la instalación ni
    aprende (409) si ya está vinculada a otra org."""
    from src.jira.integrations_repository import InstallationAlreadyBound
    integ = MagicMock()
    integ.upsert_github_config.side_effect = InstallationAlreadyBound("ya vinculada")
    r = _client(integ, _verifier(has=False)).post(
        "/v2/integrations/github", json=_body(state=_state(), code="c"))
    assert r.status_code == 403
    integ.upsert_github_config.assert_not_called()


def test_codigo_rechazado_por_github_403():
    integ = MagicMock()
    r = _client(integ, _verifier(error=GitHubAuthError("bad code"))).post(
        "/v2/integrations/github", json=_body(state=_state(), code="c"))
    assert r.status_code == 403
    integ.upsert_github_config.assert_not_called()


def test_oauth_sin_configurar_503():
    integ = MagicMock()
    r = _client(integ, _verifier(configured=False)).post(
        "/v2/integrations/github", json=_body(state=_state(), code="c"))
    assert r.status_code == 503
    integ.upsert_github_config.assert_not_called()


def test_cuenta_distinta_sigue_dando_403():
    integ = MagicMock()
    r = _client(integ, _verifier(), gh_auth=_gh_auth("attacker")).post(
        "/v2/integrations/github", json=_body(state=_state(), code="c"))
    assert r.status_code == 403
    integ.upsert_github_config.assert_not_called()


def test_install_url_lleva_state_firmado(monkeypatch):
    monkeypatch.setattr(api_v2, "GITHUB_APP_SLUG", "mnemo-qa")
    monkeypatch.setattr(api_v2, "GITHUB_APP_CLIENT_ID", "Iv1.abc")
    r = _client(MagicMock(), _verifier()).get("/v2/integrations/github/install-url?org_id=o1")
    assert r.status_code == 200
    data = r.json()
    assert data["install_url"].startswith("https://github.com/apps/mnemo-qa/installations/new?state=")
    assert "client_id=Iv1.abc" in data["authorize_url"]
    from src.ci.github_install_proof import verify_install_state
    verify_install_state(data["state"], org_id="o1", user_id="user-1")


def test_install_url_sin_app_configurada_503(monkeypatch):
    monkeypatch.setattr(api_v2, "GITHUB_APP_SLUG", "")
    r = _client(MagicMock(), _verifier()).get("/v2/integrations/github/install-url?org_id=o1")
    assert r.status_code == 503


def test_campos_de_prueba_acotados():
    r = _client(MagicMock(), _verifier()).post(
        "/v2/integrations/github", json=_body(state="x" * 5000, code="c"))
    assert r.status_code == 422
