import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import jwt
import requests

from src.config import GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY

_API = "https://api.github.com"


class GitHubAuthError(RuntimeError):
    """Credenciales de la GitHub App ausentes/ inválidas o fallo al pedir el token."""


def _parse_expiry(value: Optional[str]) -> float:
    if not value:
        return time.time() + 3000.0
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class GitHubAppAuth:
    """Autenticación de la GitHub App: JWT firmado con la private key (env) →
    installation access token efímero, cacheado por installation_id."""

    def __init__(self, *, app_id: str = GITHUB_APP_ID,
                 private_key: str = GITHUB_APP_PRIVATE_KEY,
                 session: Optional[object] = None):
        self._app_id = app_id
        self._private_key = private_key
        self._session = session if session is not None else requests
        self._cache: Dict[str, Tuple[str, float]] = {}

    def app_jwt(self) -> str:
        if not self._app_id or not self._private_key:
            raise GitHubAuthError("GitHub App no configurada (GITHUB_APP_ID/PRIVATE_KEY)")
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": self._app_id}  # exp ≤ 10 min
        try:
            return jwt.encode(payload, self._private_key, algorithm="RS256")
        except Exception as exc:  # clave malformada
            raise GitHubAuthError("private key de la GitHub App inválida") from exc

    def installation_token(self, installation_id: str) -> str:
        cached = self._cache.get(installation_id)
        if cached and cached[1] - time.time() > 300:
            return cached[0]
        resp = self._session.post(
            f"{_API}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self.app_jwt()}",
                     "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubAuthError(f"installation token falló: HTTP {resp.status_code}")
        data = resp.json()
        token = data.get("token")
        if not token:
            raise GitHubAuthError("respuesta de installation token sin 'token'")
        self._cache[installation_id] = (token, _parse_expiry(data.get("expires_at")))
        return token
