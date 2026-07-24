"""Siembra de la demo de Mnemo: 2 orgs + 4 escenarios pre-procesados + baseline verde de test_perfil.

Produce:
  - Org A "Demo MTP"   → flaky + maintenance (green→red) + real + baseline verde de test_perfil,
                         todos triados + certificados
  - Org B "Cliente Beta" → run real propio (aislamiento)
  - fresh_push.json    → NO ingerido (munición del Acto 1 en vivo)

Idempotente: si Org A ya existe para este demo_user_id devuelve {"skipped": True}.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import psycopg

from src.certify.repository import CertificateRepository
from src.certify.service import CertificateService
from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact, CiTestResult
from src.config import LLM_MODEL, MNEMO_SIGNING_PRIVATE_KEY, MNEMO_SIGNING_PUBLIC_KEY, MNEMO_VERSION
from src.defects.repository import AssuranceRepository
from src.triage.service import TriageService

_FIX = pathlib.Path(__file__).parent.parent.parent / "scripts" / "demo_fixtures"

_PAD_TOTAL = 40  # tamaño plausible de una suite; los runs se rellenan hasta aquí con tests que pasan


def _padded(art: CiRunArtifact, total: int = _PAD_TOTAL) -> CiRunArtifact:
    """Rellena la suite con tests que pasan hasta `total`, para un manifiesto con cuerpo.
    No toca los tests existentes (los fallos que dirigen el triaje se conservan primero)."""
    have = len(art.tests)
    if have >= total:
        return art
    pad = [CiTestResult(test_name=f"test_suite_case_{i:03d}", status="pass") for i in range(total - have)]
    return art.model_copy(update={"tests": [*art.tests, *pad]})


def _trend_artifact(*, org_id: str, project: str, commit: str, n_pass: int,
                    failures: "list[CiTestResult] | None" = None) -> CiRunArtifact:
    """Un run de tendencia: n_pass tests que pasan + fallos opcionales (firmas conocidas)."""
    tests = [CiTestResult(test_name=f"test_suite_case_{i:03d}", status="pass") for i in range(n_pass)]
    tests.extend(failures or [])
    return CiRunArtifact(project=project, org_id=org_id, commit_sha=commit, source="playwright", tests=tests)


# Firmas de fallo conocidas (su test_name mapea a las familias que etiqueta seed_knowledge).
_FAIL_EXPORT = CiTestResult(test_name="test_export_csv", status="fail", error_type="AssertionError",
                            message="expected status 200 but got 500", file="tests/export.spec.ts", line=88)
_FAIL_CHECKOUT = CiTestResult(test_name="test_checkout_guest", status="fail", error_type="TimeoutError",
                              message="waiting for payment widget timed out", file="tests/checkout.spec.ts", line=42)
_FAIL_LOGIN = CiTestResult(test_name="test_login_submit", status="fail", error_type="ElementNotFound",
                           message="selector #submit not found", file="tests/login.spec.ts", line=15)


def _load_artifact(name: str, org_id: str) -> CiRunArtifact:
    data = json.loads((_FIX / name).read_text())
    data["org_id"] = org_id
    return CiRunArtifact.model_validate(data)


# Serie de tendencia (orden = cronológico, más antiguos primero). El último es todo-verde
# → el héroe "Última release" muestra APTO. Los fallos reutilizan firmas conocidas.
_TREND = [
    ("demo-trend-01", 38, [_FAIL_EXPORT]),
    ("demo-trend-02", 40, []),
    ("demo-trend-03", 36, [_FAIL_CHECKOUT, _FAIL_EXPORT]),
    ("demo-trend-04", 41, []),
    ("demo-trend-05", 39, [_FAIL_LOGIN]),
    ("demo-trend-06", 42, []),
    ("demo-trend-07", 43, []),
]


def _backdate_runs(db_url: str, run_ids: "list[str]") -> None:
    """Reparte los created_at de los runs (en orden) sobre las últimas ~3 semanas.
    El primero (más antiguo) ~21 días atrás; el último, hoy."""
    now = datetime.now(timezone.utc)
    n = len(run_ids)
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        for i, rid in enumerate(run_ids):
            days_ago = (n - 1 - i) * 21 / max(1, n - 1)
            cur.execute("update public.test_runs set created_at = %s where id = %s",
                        (now - timedelta(days=days_ago), rid))
        conn.commit()


def _create_org(cur: Any, name: str, user_id: str) -> str:
    cur.execute(
        "insert into public.organizations (name, created_by) values (%s,%s) returning id",
        (name, user_id),
    )
    return str(cur.fetchone()[0])


def seed_demo(*, db_url: str, demo_user_id: str) -> Dict[str, Any]:
    """Siembra Org A (5 runs: flaky + maintenance green→red + real + baseline verde de test_perfil) + Org B (aislamiento). Idempotente.
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

    # -- Org A: 5 escenarios narrativos (con padding) + serie de tendencia -----
    runs = []
    ordered_run_ids: list[str] = []
    for name in ("maintenance_green.json", "maintenance_red.json", "flaky.json", "real.json", "perfil_green.json"):
        art = _padded(_load_artifact(name, org_a))
        res = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        run_id = res["run_id"]
        triage.triage_run(user_id=demo_user_id, run_id=run_id)
        try:
            cert_svc.generate(user_id=demo_user_id, run_id=run_id,
                              created_at=datetime.now(timezone.utc).isoformat())
        except Exception:  # noqa: BLE001 — cert opcional (p.ej. sin clave de firma)
            pass
        runs.append({"fixture": name, "run_id": run_id})
        ordered_run_ids.append(run_id)

    for commit, n_pass, failures in _TREND:
        art = _trend_artifact(org_id=org_a, project="checkout-suite", commit=commit,
                              n_pass=n_pass, failures=failures)
        res = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        run_id = res["run_id"]
        triage.triage_run(user_id=demo_user_id, run_id=run_id)
        try:
            cert_svc.generate(user_id=demo_user_id, run_id=run_id,
                              created_at=datetime.now(timezone.utc).isoformat())
        except Exception:  # noqa: BLE001
            pass
        runs.append({"fixture": commit, "run_id": run_id})
        ordered_run_ids.append(run_id)

    # -- Backdating: reparte created_at en ~21 días (orden de ingesta = cronológico).
    #    Es un UPDATE POSTERIOR a toda la ingesta → no altera el orden de ingesta.
    _backdate_runs(db_url, ordered_run_ids)

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
