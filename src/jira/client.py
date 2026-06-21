from typing import List

from atlassian import Jira

from src.jira.models import JiraBug, adf_to_text


class JiraApiError(Exception):
    """Error al hablar con la API de Jira (red, auth, etc.)."""


class JiraApiClient:
    def __init__(self, base_url: str, email: str, token: str):
        self._jira = Jira(url=base_url, username=email, password=token, cloud=True)

    def fetch_bugs(self, jql: str, *, page_size: int = 50, max_issues: int = 1000) -> List[JiraBug]:
        bugs: List[JiraBug] = []
        start = 0
        base = self._jira.url.rstrip("/")
        try:
            while len(bugs) < max_issues:
                result = self._jira.jql(
                    jql, start=start, limit=page_size,
                    fields="summary,description,issuetype,status",
                )
                issues = result.get("issues") or []
                if not issues:
                    break
                for issue in issues:
                    fields = issue.get("fields") or {}
                    bugs.append(JiraBug(
                        key=issue.get("key") or "",
                        summary=(fields.get("summary") or "").strip(),
                        description=adf_to_text(fields.get("description")),
                        issue_type=(fields.get("issuetype") or {}).get("name") or "",
                        status=(fields.get("status") or {}).get("name") or "",
                        url=f"{base}/browse/{issue.get('key')}",
                    ))
                    if len(bugs) >= max_issues:
                        break
                start += len(issues)
                if start >= (result.get("total") or 0):
                    break
        except Exception as exc:  # noqa: BLE001 — envolvemos cualquier fallo de la librería
            raise JiraApiError(str(exc)) from exc
        return bugs
