"""La memoria de defectos de checkout-suite: fallos que vuelven, con su lección.

Integration: org desechable «Demo MTP» contra la BD real, cleanup total. Comprueba
que la siembra hace recurrentes las familias (por el camino real de la ingesta),
engancha la lección del PSP a la familia de timeouts y es idempotente."""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.ci.models import CiTestResult  # noqa: E402
from src.continuity.index import compute_index  # noqa: E402
from src.demo.seed_recurrencia import LECCION_PSP, RECURRENTES, seed_recurrencia  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.integration

_FALLOS = {
    "test_checkout_flujo": ("TimeoutError", "Timeout 30000ms waiting for #cart"),
    "test_login": ("NoSuchElementError", "locator not found: #submit"),
    "test_export_csv": ("AssertionError", "expected status 200 but got 500"),
}


@pytest.fixture()
def org_con_fallos_base():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    from src.ci.ingestion_service import CiIngestionService
    from src.defects.embedder import LocalEmbedder
    from src.defects.repository import AssuranceRepository
    from src.demo.seed import _trend_artifact

    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"seedr-{user[:8]}@test.internal"))
        cur.execute("insert into public.organizations (name, created_by)"
                    " values ('Demo MTP',%s) returning id", (user,))
        org = str(cur.fetchone()[0])
        cur.execute("insert into public.qa_knowledge (org_id, kind, title, approach, project,"
                    " created_by) values (%s,'leccion',%s,'Mirar X-RateLimit-Remaining antes"
                    " de culpar al test.','checkout-suite',%s)", (org, LECCION_PSP, user))
        conn.commit()
    fallos = [CiTestResult(test_name=t, status="fail", error_type=e, message=m)
              for t, (e, m) in _FALLOS.items()]
    art = _trend_artifact(org_id=org, project="checkout-suite", commit="base", n_pass=3,
                          failures=fallos)
    CiIngestionService(repo=AssuranceRepository(DBURL), embedder=LocalEmbedder()).ingest_artifact(
        user_id=user, artifact=art.model_copy(update={"run_uid": "base-1"}))
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def _familias(org):
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select fl.test_name, df.occurrence_count, df.id from public.failures fl"
                    " join public.defect_families df on df.id = fl.defect_family_id"
                    " where fl.org_id = %s", (org,))
        return {t: (n, str(i)) for t, n, i in cur.fetchall()}


def test_los_fallos_vuelven_y_la_leccion_queda_enganchada(org_con_fallos_base):
    ctx = org_con_fallos_base
    out = seed_recurrencia(db_url=DBURL, demo_user_id=ctx["user"])
    assert out["runs_creados"] == 2 and out["lecciones_enlazadas"] == 1
    fams = _familias(ctx["org"])
    assert all(fams[t][0] >= 3 for t in RECURRENTES)   # base + 2 runs → recurrentes
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select defect_family_id::text from public.qa_knowledge where org_id=%s"
                    " and title=%s", (ctx["org"], LECCION_PSP))
        assert cur.fetchone()[0] == fams["test_checkout_flujo"][1]
    idx = compute_index(user_id=ctx["user"], org_id=ctx["org"], project="checkout-suite")
    mem = {d["key"]: d for d in idx["dimensions"]}["memoria_defectos"]
    # 3 recurrentes; solo la de timeouts tiene conocimiento en esta org de prueba.
    assert (mem["num"], mem["den"]) == (1, 3)


def test_segunda_pasada_no_crea_nada(org_con_fallos_base):
    ctx = org_con_fallos_base
    seed_recurrencia(db_url=DBURL, demo_user_id=ctx["user"])
    antes = _familias(ctx["org"])
    out = seed_recurrencia(db_url=DBURL, demo_user_id=ctx["user"])
    assert out["runs_creados"] == 0 and out["lecciones_enlazadas"] == 0
    assert _familias(ctx["org"]) == antes
