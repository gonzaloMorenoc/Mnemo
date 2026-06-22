from dataclasses import replace
from typing import Any, Dict

from src.ci.mapping import to_failure_records
from src.ci.models import CiRunArtifact
from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.sanitizer import sanitize_text


class CiIngestionService:
    """Orquesta la ingesta de un artefacto de CI: fallos → Defect DNA, más
    resultados por test y snapshots DOM (cimientos para el triaje de F2/F3)."""

    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder):
        self.repo = repo
        self.embedder = embedder

    def ingest_artifact(self, *, user_id: str, artifact: CiRunArtifact) -> Dict[str, Any]:
        items = []
        for rec in to_failure_records(artifact):
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            embedding = self.embedder.embed(f"{clean.error_type or ''} {message}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=embedding))

        result = self.repo.ingest_run(
            user_id=user_id, org_id=artifact.org_id, project=artifact.project,
            source=artifact.source, items=items, commit_sha=artifact.commit_sha,
        )
        run_id = result["run_id"]

        results = [
            {"test_name": t.test_name, "status": t.status, "retried": t.retried}
            for t in artifact.tests
        ]
        self.repo.record_test_results(
            user_id=user_id, org_id=artifact.org_id, run_id=run_id, results=results,
        )

        snapshots = [
            {
                "test_name": t.test_name,
                "kind": "last_green" if t.status == "pass" else "failure",
                "content": t.dom,
                "commit_sha": artifact.commit_sha,
            }
            for t in artifact.tests
            if t.dom
        ]
        snapshots_saved = 0
        if snapshots:
            snapshots_saved = self.repo.save_dom_snapshots(
                user_id=user_id, org_id=artifact.org_id, project=artifact.project,
                snapshots=snapshots,
            )

        return {
            **result,
            "results_recorded": len(results),
            "snapshots_saved": snapshots_saved,
        }
