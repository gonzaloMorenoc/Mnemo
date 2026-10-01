"""La memoria de defectos de checkout-suite: fallos que vuelven, con su lección.

El 95 de checkout-suite salía con «memoria de defectos 0/0»: sus cuatro familias
tenían una sola aparición y la dimensión solo cuenta las RECURRENTES. El número
estrella de la demo se apoyaba en runbooks y contactos —lo que tendría una wiki— y
no en lo que la distingue: el enlace entre lo que falla en el CI y lo que el equipo
aprendió de ello.

Aquí, por el mismo camino que la app (ingesta real, triaje del motor, acta firmada):
  1. la lección del rate-limit del sandbox del PSP queda enganchada a la familia de
     los timeouts de checkout (la de la razón de María);
  2. dos runs nuevos repiten tres fallos reales del proyecto: los timeouts del PSP
     (con lección), el selector #submit (con conocimiento) y el error de exportación
     CSV (SIN lección: un hueco honesto que el índice enseña con su «Revisar»).

Idempotente: run_uid fijos y el enlace solo se hace si la lección aún no lo tiene.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg

from src.ci.models import CiTestResult
from src.demo.seed_knowledge import _load_orgs

PROJECT = "checkout-suite"
# Fallos reales del proyecto que vuelven a ocurrir (verbatim de la BD → mismo
# fingerprint → misma familia: crecen las recurrentes, no nacen familias nuevas).
RECURRENTES = ("test_checkout_flujo", "test_login", "test_export_csv")
# La lección que explica la familia de timeouts (src/demo/continuity_data.py).
LECCION_PSP = "Los fallos intermitentes del sandbox del PSP se diagnostican por el rate-limit"
TEST_TIMEOUTS = "test_checkout_flujo"
RUNS = (("continuidad-recurrencia-1", 12), ("continuidad-recurrencia-2", 5))  # (uid, días atrás)
N_PASS = 40


def _firmas(cur, org_id: str) -> List[CiTestResult]:
    cur.execute(
        "select distinct on (fl.test_name) fl.test_name, fl.error_type, fl.message, fl.trace"
        " from public.failures fl join public.test_runs tr on tr.id = fl.run_id"
        " where tr.org_id = %s and tr.project = %s and fl.test_name = any(%s)"
        " order by fl.test_name, fl.created_at", (org_id, PROJECT, list(RECURRENTES)))
    return [CiTestResult(test_name=r[0], status="fail", error_type=r[1], message=r[2],
                         trace=r[3]) for r in cur.fetchall()]


def _enlazar_leccion(cur, org_id: str) -> int:
    """La lección del PSP apunta a la familia de los timeouts de checkout."""
    cur.execute(
        "update public.qa_knowledge k set defect_family_id = fam.id"
        " from (select fl.defect_family_id as id from public.failures fl"
        "       join public.test_runs tr on tr.id = fl.run_id"
        "       where tr.org_id = %s and tr.project = %s and fl.test_name = %s"
        "         and fl.defect_family_id is not null limit 1) fam"
        " where k.org_id = %s and k.kind = 'leccion' and k.title = %s"
        "   and k.defect_family_id is null",
        (org_id, PROJECT, TEST_TIMEOUTS, org_id, LECCION_PSP))
    return cur.rowcount


def seed_recurrencia(*, db_url: str, demo_user_id: str, until: Optional[date] = None,
                     signing_private_key: Optional[str] = None,
                     signing_public_key: Optional[str] = None) -> Dict[str, Any]:
    until = until or date.today()
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        orgs = _load_orgs(cur, demo_user_id)
        if "Demo MTP" not in orgs:
            return {"skipped": True, "reason": "ejecuta seed_demo primero"}
        org = orgs["Demo MTP"]
        enlazadas = _enlazar_leccion(cur, org)
        firmas = _firmas(cur, org)
        conn.commit()
    if len(firmas) != len(RECURRENTES):
        return {"skipped": True, "reason": f"faltan fallos base: {len(firmas)}/{len(RECURRENTES)}",
                "lecciones_enlazadas": enlazadas}

    # Imports tardíos: el embedder carga torch y solo hace falta al sembrar.
    from src.ci.ingestion_service import CiIngestionService
    from src.defects.embedder import LocalEmbedder
    from src.defects.repository import AssuranceRepository
    from src.demo.seed import _trend_artifact
    from src.demo.seed_riqueza import _certificar_runs

    arepo = AssuranceRepository(db_url)
    ingest = CiIngestionService(repo=arepo, embedder=LocalEmbedder())
    nuevos = []
    for uid, dias in RUNS:
        art = _trend_artifact(org_id=org, project=PROJECT, commit=f"rec{dias:02d}chk",
                              n_pass=N_PASS, failures=firmas)
        res = ingest.ingest_artifact(user_id=demo_user_id,
                                     artifact=art.model_copy(update={"run_uid": uid}))
        if not res.get("deduplicated"):
            nuevos.append((res["run_id"], until - timedelta(days=dias)))
    if nuevos:  # fechar cada run en su día (UPDATE posterior, patrón seed.py)
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            for run_id, fecha in nuevos:
                cur.execute("update public.test_runs set created_at=%s where id=%s",
                            (datetime.combine(fecha, time(11, 15), tzinfo=timezone.utc), run_id))
            conn.commit()
    actas = _certificar_runs(db_url, org_id=org, user_id=demo_user_id, arepo=arepo,
                             private_key=signing_private_key, public_key=signing_public_key)
    return {"lecciones_enlazadas": enlazadas, "runs_creados": len(nuevos), "actas": actas}
