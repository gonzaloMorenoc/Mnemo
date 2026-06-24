from typing import List, Optional

import requests

from src.ci.github_auth import GitHubAppAuth

_API = "https://api.github.com"


class GitHubError(RuntimeError):
    """Fallo de la API REST de GitHub al materializar un artefacto."""


class GitHubCodeHost:
    """CodeHost real: crea Issues en el repo del org. Idempotente por marcador oculto
    en el body (no duplica al reintentar). open_draft_pr llega en F3c-2."""

    def __init__(self, *, auth: GitHubAppAuth, installation_id: str,
                 repo_full_name: str, session: Optional[object] = None):
        self._auth = auth
        self._installation_id = installation_id
        self._repo = repo_full_name
        self._session = session if session is not None else requests

    def _headers(self) -> dict:
        token = self._auth.installation_token(self._installation_id)
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def _find_by_marker(self, marker: str) -> Optional[str]:
        resp = self._session.get(
            f"{_API}/search/issues",
            params={"q": f'repo:{self._repo} in:body "{marker}"'},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            return None  # búsqueda no disponible → seguimos a crear
        items = resp.json().get("items", [])
        return items[0]["html_url"] if items else None

    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str:
        if marker:
            existing = self._find_by_marker(marker)
            if existing:
                return existing
            body = f"{body}\n\n<!-- {marker} -->"
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/issues",
            json={"title": title, "body": body, "labels": labels},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"crear issue falló: HTTP {resp.status_code}")
        return resp.json()["html_url"]

    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str:
        raise NotImplementedError("open_draft_pr (self-heal → PR) es F3c-2")
