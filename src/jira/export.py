import csv
import io
import json
from typing import List

from src.jira.models import JiraBug, adf_to_text


def _from_search_json(obj: dict) -> List[JiraBug]:
    bugs: List[JiraBug] = []
    for issue in obj.get("issues") or []:
        fields = issue.get("fields") or {}
        itype = (fields.get("issuetype") or {}).get("name") or ""
        if itype.lower() != "bug":
            continue
        bugs.append(JiraBug(
            key=issue.get("key") or "",
            summary=(fields.get("summary") or "").strip(),
            description=adf_to_text(fields.get("description")),
            issue_type=itype,
            status=(fields.get("status") or {}).get("name") or "",
        ))
    return bugs


def _from_csv(text: str) -> List[JiraBug]:
    bugs: List[JiraBug] = []
    for row in csv.DictReader(io.StringIO(text)):
        itype = (row.get("Issue Type") or "").strip()
        if itype.lower() != "bug":
            continue
        bugs.append(JiraBug(
            key=(row.get("Issue key") or "").strip(),
            summary=(row.get("Summary") or "").strip(),
            description=(row.get("Description") or "").strip(),
            issue_type=itype,
            status=(row.get("Status") or "").strip(),
        ))
    return bugs


def parse_jira_export(data: bytes) -> List[JiraBug]:
    """Parsea un export de Jira: JSON de /rest/api/3/search o CSV estándar. Solo Bugs."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Invalid Jira export encoding: {exc}") from exc
    stripped = text.lstrip()
    if stripped[:1] == "{":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Jira JSON: {exc}") from exc
        return _from_search_json(obj)
    first_line = stripped.splitlines()[0] if stripped else ""
    if "Issue key" not in first_line:
        raise ValueError("Unrecognized Jira export (expected search JSON or CSV with 'Issue key')")
    return _from_csv(text)
