"""Siembra de la demo de Mnemo: 2 orgs + 3 escenarios pre-procesados.

Produce:
  - Org A "Demo MTP"   → flaky + maintenance (green→red) + real, todos triados + certificados
  - Org B "Cliente Beta" → run real propio (aislamiento)
  - fresh_push.json    → NO ingerido (munición del Acto 1 en vivo)

Idempotente: si Org A ya existe para este demo_user_id devuelve {"skipped": True}.
"""

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict

import psycopg

from src.certify.repository import CertificateRepository
from src.certify.service import CertificateService
from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact
from src.config import LLM_MODEL, MNEMO_SIGNING_PRIVATE_KEY, MNEMO_SIGNING_PUBLIC_KEY, MNEMO_VERSION
from src.defects.repository import AssuranceRepository
from src.triage.service import TriageService

_FIX = pathlib.Path(__file__).parent.parent.parent / "scripts" / "demo_fixtures"


def _load_artifact(name: str, org_id: str) -> CiRunArtifact:
    data = json.loads((_FIX / name).read_text())
    data["org_id"] = org_id
    return CiRunArtifact.model_validate(data)


def _create_org(cur: Any, name: str, user_id: str) -> str:
    cur.execute(
        "insert into public.organizations (name, created_by) values (%s,%s) returning id",
        (name, user_id),
    )
    return str(cur.fetchone()[0])


def seed_demo(*, db_url: str, demo_user_id: str) -> Dict[str, Any]:
    """Siembra Org A (3 escenarios pre-procesados) + Org B (aislamiento). Idempotente.
    Devuelve un resumen con {org_a, org_b, runs, fresh_artifact_path}.
    Si Org A ya existe para este usuario devuelve {"skipped": True}.
    """
    # -- Idempotency check + org creation (atomic) ---------------------------
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id from public.organizations where created_by=%s and name=%s",
                (demo_user_id, "Demo MTP"),
            )
            if cur.fetchone():
                return {"skipped": True}
            org_a = _create_org(cur, "Demo MTP", demo_user_id)
            org_b = _create_org(cur, "Cliente Beta", demo_user_id)
        conn.commit()

    # -- Service construction (mirrors api_v2.get_*) -------------------------
    from src.defects.embedder import LocalEmbedder

    repo = AssuranceRepository(db_url)
    cert_repo = CertificateRepository(db_url)
    embedder = LocalEmbedder()

    ingest = CiIngestionService(repo=repo, embedder=embedder)
    triage = TriageService(repo=repo)

    llm = None  # sin ai_eval en el seed

    cert_svc = CertificateService(
        repo=repo,
        cert_repo=cert_repo,
        private_key=MNEMO_SIGNING_PRIVATE_KEY,
        public_key=MNEMO_SIGNING_PUBLIC_KEY,
        mnemo_version=MNEMO_VERSION,
        model_version=LLM_MODEL or "unknown",
        llm_provider=llm,
    )

    # -- Org A: 4 runs (orden crítico: maintenance_green antes que red) ------
    runs = []
    for name in ("maintenance_green.json", "maintenance_red.json", "flaky.json", "real.json", "perfil_green.json"):
        art = _load_artifact(name, org_a)
        res = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        run_id = res["run_id"]
        triage.triage_run(user_id=demo_user_id, run_id=run_id)
        try:
            cert_svc.generate(
                user_id=demo_user_id,
                run_id=run_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception:  # noqa: BLE001 — cert opcional (p.ej. sin clave de firma)
            pass
        runs.append({"fixture": name, "run_id": run_id})

    # -- Org B: un run real propio (aislamiento) -----------------------------
    for name in ("real.json",):
        art = _load_artifact(name, org_b)
        r = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        triage.triage_run(user_id=demo_user_id, run_id=r["run_id"])

    return {
        "org_a": org_a,
        "org_b": org_b,
        "runs": runs,
        "fresh_artifact_path": str(_FIX / "fresh_push.json"),
    }
