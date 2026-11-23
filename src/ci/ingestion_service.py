import hashlib
from typing import Any, Dict

from src.ci.mapping import to_failure_records
from src.ci.models import CiRunArtifact
from src.defects.embedder import Embedder
from src.defects.item_prep import build_ingest_item
from src.defects.repository import AssuranceRepository


class CiIngestionService:
    """Orquesta la ingesta de un artefacto de CI: fallos → Defect DNA, más
    resultados por test y snapshots DOM (cimientos para el triaje de F2/F3)."""

    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder):
        self.repo = repo
        self.embedder = embedder

    def ingest_artifact(self, *, user_id: str, artifact: CiRunArtifact) -> Dict[str, Any]:
        """Ingesta atómica e idempotente de un artefacto de CI: fallos→Defect DNA +
        resultados por test + snapshots DOM, en una sola transacción. Idempotente por run_uid.
        Nota: la idempotencia (dedup por run_uid) solo se activa si el reporter emite run_uid;
        si es None, solo aplica atomicidad (retrocompatible)."""
        # Membresía ANTES de embeber (03-técnica E9); la definitiva sigue en la transacción.
        if not self.repo.is_member(user_id=user_id, org_id=artifact.org_id):
            raise PermissionError("user is not a member of the organization")
        # Huella del crudo, guardado y embedding del saneado (auditoría 23-nov, #3).
        items = [build_ingest_item(rec, self.embedder) for rec in to_failure_records(artifact)]

        results = [
            {"test_name": t.test_name, "status": t.status, "retried": t.retried}
            for t in artifact.tests
        ]
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

        counts = {"pass": 0, "fail": 0, "flaky": 0, "skipped": 0}
        for t in artifact.tests:
            counts[t.status] = counts.get(t.status, 0) + 1
        total = len(artifact.tests)
        manifest = {
            "total": total, "passed": counts["pass"], "failed": counts["fail"],
            "skipped": counts["skipped"], "flaky": counts["flaky"], "complete": total > 0,
            "source_format": artifact.source,
            "artifact_sha256": hashlib.sha256(artifact.model_dump_json().encode()).hexdigest(),
            "commit_sha": artifact.commit_sha,
        }

        return self.repo.ingest_ci_run(
            user_id=user_id, org_id=artifact.org_id, project=artifact.project,
            source=artifact.source, commit_sha=artifact.commit_sha, run_uid=artifact.run_uid,
            items=items, results=results, snapshots=snapshots, manifest=manifest,
        )
