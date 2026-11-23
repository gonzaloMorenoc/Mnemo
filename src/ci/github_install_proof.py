"""Prueba de posesión al vincular una instalación de la GitHub App (auditoría 23-nov, H4).

Antes, vincular solo comprobaba que la cuenta de la instalación coincidía con el
dueño del repo: quien reclamaba primero un `installation_id` ajeno (son enteros
enumerables) se lo quedaba. Ahora, en multi-tenant, hacen falta dos pruebas:

1. `state` firmado (HMAC-SHA256 con un secreto de servidor), ligado a la org y al
   usuario que inician la vinculación y con caducidad corta. Lo emite
   `GET /v2/integrations/github/install-url` y GitHub lo devuelve en el callback.
2. Verificación con la API de GitHub: el `code` OAuth que GitHub entrega en el
   callback (con «Request user authorization (OAuth) during installation» activado
   en la App) se canjea por un token de usuario y se comprueba que la instalación
   está en `GET /user/installations`, es decir, que ese usuario de GitHub tiene
   acceso a ella. El `state` solo no basta: el `installation_id` del callback no
   va firmado por GitHub y se podría cambiar a mano.

El código OAuth es de un solo uso, así que reutilizar un `state` no sirve de nada.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

import requests

from src.ci.github_auth import GitHubAuthError

STATE_TTL_SECONDS = 600            # 10 min: lo que dura una instalación en GitHub
_STATE_VERSION = 1
_STATE_DOMAIN = b"mnemo:github-install-state:v1:"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_INSTALLATIONS_URL = "https://api.github.com/user/installations"
_PAGE_SIZE = 100
_MAX_PAGES = 10                    # 1.000 instalaciones visibles por usuario: de sobra
_HTTP_TIMEOUT_SECONDS = 15


class GitHubProofNotConfigured(RuntimeError):
    """Falta el secreto del `state` o las credenciales OAuth de la GitHub App."""


class InvalidInstallState(ValueError):
    """`state` ausente, manipulado, caducado o de otra org/usuario."""


def _state_secret(explicit: Optional[str]) -> bytes:
    if explicit:
        return explicit.encode("utf-8")
    dedicated = os.getenv("GITHUB_STATE_SECRET", "")
    if dedicated:
        return dedicated.encode("utf-8")
    base = os.getenv("MNEMO_SECRET_KEY", "")
    if base:
        # Derivado con separación de dominio: no reutiliza la clave Fernet tal cual.
        return hashlib.sha256(_STATE_DOMAIN + base.encode("utf-8")).digest()
    raise GitHubProofNotConfigured(
        "sin GITHUB_STATE_SECRET ni MNEMO_SECRET_KEY no se puede firmar el state")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: bytes, payload: str) -> str:
    return _b64(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())


def sign_install_state(org_id: str, user_id: str, *, now: Optional[float] = None,
                       secret: Optional[str] = None) -> str:
    issued = int(time.time() if now is None else now)
    body = {"v": _STATE_VERSION, "o": org_id, "u": user_id,
            "e": issued + STATE_TTL_SECONDS, "n": secrets.token_urlsafe(8)}
    payload = _b64(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_mac(_state_secret(secret), payload)}"


def verify_install_state(state: str, *, org_id: str, user_id: str,
                         now: Optional[float] = None, secret: Optional[str] = None) -> None:
    parts = (state or "").split(".")
    if len(parts) != 2 or not all(parts):
        raise InvalidInstallState("state con formato inválido")
    payload, mac = parts
    if not hmac.compare_digest(mac, _mac(_state_secret(secret), payload)):
        raise InvalidInstallState("firma del state inválida")
    try:
        body = json.loads(_unb64(payload))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidInstallState("state ilegible") from exc
    current = time.time() if now is None else now
    if body.get("v") != _STATE_VERSION or not isinstance(body.get("e"), int):
        raise InvalidInstallState("versión de state desconocida")
    if body["e"] < current:
        raise InvalidInstallState("state caducado: vuelve a iniciar la vinculación")
    if body.get("o") != org_id or body.get("u") != user_id:
        raise InvalidInstallState("el state es de otra organización o de otro usuario")


class GitHubUserInstallationVerifier:
    """¿Tiene el usuario de GitHub que autorizó (code OAuth) acceso a la instalación?"""

    def __init__(self, *, client_id: str, client_secret: str, session: Optional[object] = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._session = session if session is not None else requests

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def _user_token(self, code: str) -> str:
        resp = self._session.post(
            _TOKEN_URL,
            data={"client_id": self._client_id, "client_secret": self._client_secret,
                  "code": code},
            headers={"Accept": "application/json"},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        token = resp.json().get("access_token") if resp.status_code < 300 else None
        if not token:
            raise GitHubAuthError("GitHub rechazó el código de autorización")
        return token

    def _installation_ids(self, token: str, page: int) -> list:
        resp = self._session.get(
            _USER_INSTALLATIONS_URL,
            params={"per_page": _PAGE_SIZE, "page": page},
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json"},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code >= 300:
            raise GitHubAuthError(f"no se pudieron listar las instalaciones: HTTP {resp.status_code}")
        return [str(item.get("id")) for item in resp.json().get("installations") or []]

    def user_has_installation(self, *, code: str, installation_id: str) -> bool:
        if not self.configured:
            raise GitHubProofNotConfigured(
                "faltan GITHUB_APP_CLIENT_ID / GITHUB_APP_CLIENT_SECRET")
        token = self._user_token(code)
        for page in range(1, _MAX_PAGES + 1):
            ids = self._installation_ids(token, page)
            if str(installation_id) in ids:
                return True
            if len(ids) < _PAGE_SIZE:
                return False
        return False
