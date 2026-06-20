from dataclasses import replace
from typing import Any, Dict, List, Set

from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.jira.client import JiraApiClient
from src.jira.export import parse_jira_export
from src.jira.integrations_repository import IntegrationsRepository
from src.jira.mapper import bug_to_record
from src.jira.models import JiraBug
from src.jira.safe_url import validate_base_url
from src.sanitizer import sanitize_text


class JiraIngestionService:
    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder,
                 integrations: IntegrationsRepository):
        self.repo = repo
        self.embedder = embedder
        self.integrations = integrations

    def _to_items(self, bugs: List[JiraBug], *, project: str, seen: Set[str]) -> List[IngestItem]:
        items: List[IngestItem] = []
        for bug in bugs:
            if not bug.key or bug.key in seen:
                continue
            seen.add(bug.key)
            rec = bug_to_record(bug, project=project)
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            emb = self.embedder.embed(f"{bug.summary} {bug.description}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=emb,
                                    external_ref=bug.key, external_url=bug.url or None))
        return items

    def ingest_bugs(self, *, user_id: str, org_id: str, project: str,
                    bugs: List[JiraBug]) -> Dict[str, Any]:
        existing = self.repo.existing_external_refs(user_id=user_id, org_id=org_id)
        items = self._to_items(bugs, project=project, seen=set(existing))
        skipped = len(bugs) - len(items)
        if not items:
            return {"run_id": None, "ingested": 0, "known": 0, "novel": 0, "skipped": skipped}
        result = self.repo.ingest_run(user_id=user_id, org_id=org_id, project=project,
                                      source="jira", items=items)
        result["skipped"] = skipped
        return result

    def ingest_from_export(self, *, user_id: str, org_id: str, project: str,
                           data: bytes) -> Dict[str, Any]:
        bugs = parse_jira_export(data)
        return self.ingest_bugs(user_id=user_id, org_id=org_id, project=project, bugs=bugs)

    def ingest_from_pull(self, *, user_id: str, org_id: str, project: str) -> Dict[str, Any]:
        creds = self.integrations.get_jira_credentials(user_id=user_id, org_id=org_id)
        if creds is None:
            raise ValueError("configura la integración de Jira primero")
        validate_base_url(creds["base_url"])
        client = JiraApiClient(creds["base_url"], creds["email"], creds["token"])
        bugs = client.fetch_bugs(creds["jql"])
        return self.ingest_bugs(user_id=user_id, org_id=org_id, project=project, bugs=bugs)
