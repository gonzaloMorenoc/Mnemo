"""Prueba de posesión al vincular una instalación de la GitHub App (auditoría 23-nov,
H4): `state` firmado ligado a org+usuario y verificación con el token de usuario de
GitHub de que quien vincula tiene acceso a la instalación. Sin red: sesión simulada."""
import pytest

from src.ci.github_auth import GitHubAuthError
from src.ci.github_install_proof import (
    GitHubProofNotConfigured,
    GitHubUserInstallationVerifier,
    InvalidInstallState,
    STATE_TTL_SECONDS,
    sign_install_state,
    verify_install_state,
)

SECRET = "s" * 32


def test_state_valido():
    st = sign_install_state("org-1", "user-1", now=1000, secret=SECRET)
    verify_install_state(st, org_id="org-1", user_id="user-1", now=1001, secret=SECRET)


@pytest.mark.parametrize("org, user, now", [
    ("org-2", "user-1", 1001),                       # otra org
    ("org-1", "user-2", 1001),                       # otro usuario
    ("org-1", "user-1", 1000 + STATE_TTL_SECONDS + 1),   # caducado
])
def test_state_rechazado(org, user, now):
    st = sign_install_state("org-1", "user-1", now=1000, secret=SECRET)
    with pytest.raises(InvalidInstallState):
        verify_install_state(st, org_id=org, user_id=user, now=now, secret=SECRET)


@pytest.mark.parametrize("tamper", [
    lambda s: s[:-2] + ("AA" if not s.endswith("AA") else "BB"),
    lambda s: "x" + s,
    lambda s: s.split(".")[0],
    lambda s: "",
    lambda s: "a.b.c",
])
def test_state_manipulado(tamper):
    st = sign_install_state("org-1", "user-1", now=1000, secret=SECRET)
    with pytest.raises(InvalidInstallState):
        verify_install_state(tamper(st), org_id="org-1", user_id="user-1", now=1001, secret=SECRET)


def test_state_firmado_con_otro_secreto():
    st = sign_install_state("org-1", "user-1", now=1000, secret="otro" * 8)
    with pytest.raises(InvalidInstallState):
        verify_install_state(st, org_id="org-1", user_id="user-1", now=1001, secret=SECRET)


def test_sin_secreto_no_se_firma(monkeypatch):
    monkeypatch.delenv("GITHUB_STATE_SECRET", raising=False)
    monkeypatch.delenv("MNEMO_SECRET_KEY", raising=False)
    with pytest.raises(GitHubProofNotConfigured):
        sign_install_state("org-1", "user-1")


def test_secreto_derivado_de_mnemo_secret_key(monkeypatch):
    monkeypatch.delenv("GITHUB_STATE_SECRET", raising=False)
    monkeypatch.setenv("MNEMO_SECRET_KEY", "k" * 44)
    st = sign_install_state("org-1", "user-1")
    verify_install_state(st, org_id="org-1", user_id="user-1")


# --- verificación con el token de usuario de GitHub ---------------------------

class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, token_resp, pages):
        self.token_resp = token_resp
        self.pages = pages
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.token_resp

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        page = kw["params"]["page"]
        return self.pages[page - 1] if page <= len(self.pages) else _Resp(200, {"installations": []})


def _verifier(session):
    return GitHubUserInstallationVerifier(client_id="cid", client_secret="csecret",
                                          session=session)


def _page(ids, full=False):
    items = [{"id": i} for i in ids]
    if full:
        items += [{"id": 10_000 + n} for n in range(100 - len(ids))]
    return _Resp(200, {"installations": items})


def test_usuario_con_acceso_a_la_instalacion():
    s = _Session(_Resp(200, {"access_token": "gho_x"}), [_page([7], full=True), _page([42])])
    assert _verifier(s).user_has_installation(code="c0de", installation_id="42") is True
    post = s.calls[0]
    assert post[0] == "POST" and post[2]["data"]["code"] == "c0de"
    assert s.calls[1][2]["headers"]["Authorization"] == "Bearer gho_x"


def test_usuario_sin_acceso():
    s = _Session(_Resp(200, {"access_token": "gho_x"}), [_page([7, 8])])
    assert _verifier(s).user_has_installation(code="c", installation_id="42") is False


def test_codigo_invalido():
    s = _Session(_Resp(200, {"error": "bad_verification_code"}), [])
    with pytest.raises(GitHubAuthError):
        _verifier(s).user_has_installation(code="c", installation_id="42")


def test_fallo_al_listar_instalaciones():
    s = _Session(_Resp(200, {"access_token": "gho_x"}), [_Resp(401, {})])
    with pytest.raises(GitHubAuthError):
        _verifier(s).user_has_installation(code="c", installation_id="42")


def test_verificador_sin_configurar():
    v = GitHubUserInstallationVerifier(client_id="", client_secret="", session=_Session(None, []))
    assert v.configured is False
    with pytest.raises(GitHubProofNotConfigured):
        v.user_has_installation(code="c", installation_id="42")
