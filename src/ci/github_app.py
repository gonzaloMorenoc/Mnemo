import base64
from typing import List, Optional
from urllib.parse import quote

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

    def open_draft_pr(self, *, title: str, body: str, file_path: str,
                      old_str: str, new_str: str, marker: str = "") -> Optional[str]:
        owner = self._repo.split("/")[0]
        action_id = marker.rsplit(":", 1)[-1] if marker else "fix"
        branch = f"mnemo/self-heal/{action_id}"
        existing = self._find_pr_by_head(owner, branch)
        if existing:
            return existing
        default_branch = self._default_branch()
        base_sha = self._ref_sha(default_branch)
        content, file_sha = self._get_file(file_path, default_branch)
        new_content = content.replace(old_str, new_str, 1)
        if new_content == content:
            return None  # locator no encontrado en el archivo → degrada
        self._create_ref(branch, base_sha)
        self._put_file(file_path, new_content, file_sha, branch,
                       message=f"fix(self-heal): {old_str} -> {new_str}")
        pr_body = f"{body}\n\n<!-- {marker} -->" if marker else body
        return self._create_pr(title, pr_body, branch, default_branch)

    def open_pr_with_new_file(self, *, title: str, body: str, file_path: str,
                              content: str, marker: str = "") -> Optional[str]:
        """Crea un fichero NUEVO (o actualiza si existe) en una rama y abre un draft PR. Idempotente."""
        owner = self._repo.split("/")[0]
        slug = marker.rsplit(":", 1)[-1] if marker else "test"
        branch = f"mnemo/automation/{slug}"
        existing = self._find_pr_by_head(owner, branch)
        if existing:
            return existing
        default_branch = self._default_branch()
        base_sha = self._ref_sha(default_branch)
        try:
            _existing, file_sha = self._get_file(file_path, default_branch)
        except Exception:  # noqa: BLE001 — fichero no existe → creación
            file_sha = None
        self._create_ref(branch, base_sha)
        self._put_file(file_path, content, file_sha, branch,
                       message=f"test(automation): {file_path}")
        pr_body = f"{body}\n\n<!-- {marker} -->" if marker else body
        return self._create_pr(title, pr_body, branch, default_branch)

    def read_file(self, file_path: str) -> Optional[str]:
        """Lee el contenido de un archivo del repo (rama por defecto). None si no existe/sin acceso."""
        try:
            content, _sha = self._get_file(file_path, self._default_branch())
            return content
        except Exception:  # noqa: BLE001 — sin acceso/archivo → degrada
            return None

    def _find_pr_by_head(self, owner: str, branch: str) -> Optional[str]:
        resp = self._session.get(
            f"{_API}/repos/{self._repo}/pulls",
            params={"head": f"{owner}:{branch}", "state": "all"},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            return None
        prs = resp.json()
        return prs[0]["html_url"] if prs else None

    def _default_branch(self) -> str:
        resp = self._session.get(f"{_API}/repos/{self._repo}", headers=self._headers(), timeout=15)
        if resp.status_code >= 300:
            raise GitHubError(f"get repo falló: HTTP {resp.status_code}")
        return resp.json()["default_branch"]

    def _ref_sha(self, branch: str) -> str:
        resp = self._session.get(
            f"{_API}/repos/{self._repo}/git/ref/heads/{branch}",
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"get ref falló: HTTP {resp.status_code}")
        return resp.json()["object"]["sha"]

    def _get_file(self, file_path: str, ref: str):
        resp = self._session.get(
            f"{_API}/repos/{self._repo}/contents/{quote(file_path, safe='/')}",
            params={"ref": ref}, headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"get contents falló: HTTP {resp.status_code}")
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]

    def _create_ref(self, branch: str, sha: str) -> None:
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code == 422:
            return  # el branch ya existe → reusa
        if resp.status_code >= 300:
            raise GitHubError(f"create ref falló: HTTP {resp.status_code}")

    def _put_file(self, file_path: str, new_content: str, file_sha: Optional[str],
                  branch: str, *, message: str) -> None:
        payload: dict = {
            "message": message,
            "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if file_sha:  # omit sha when creating a new file (GitHub rejects sha=null)
            payload["sha"] = file_sha
        resp = self._session.put(
            f"{_API}/repos/{self._repo}/contents/{quote(file_path, safe='/')}",
            json=payload,
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"put contents falló: HTTP {resp.status_code}")

    def _create_pr(self, title: str, body: str, head: str, base: str) -> str:
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base, "draft": True},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"create PR falló: HTTP {resp.status_code}")
        return resp.json()["html_url"]

    def publish_check_run(self, *, head_sha: str, conclusion: str,
                          title: str, summary: str) -> str:
        """Publica un check run mnemo/assurance sobre head_sha (Checks API).
        conclusion ∈ {success, failure, neutral}. Devuelve la URL del check run."""
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/check-runs",
            json={"name": "mnemo/assurance", "head_sha": head_sha, "status": "completed",
                  "conclusion": conclusion, "output": {"title": title, "summary": summary}},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"publish check-run falló: HTTP {resp.status_code}")
        return resp.json()["html_url"]
