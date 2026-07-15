"""seed_knowledge: puebla memoria QA + causas raíz + calibración + test assets
sobre las orgs creadas por seed_demo. Integración contra BD real (patrón de
test_demo_seed.py): usuario propio + limpieza por CASCADE.
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.demo.seed import seed_demo  # noqa: E402
from src.demo.seed_knowledge import seed_knowledge  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")

ALL_KINDS = {"regla_negocio", "flujo", "riesgo", "glosario", "leccion", "reto", "patron"}


@pytest.fixture
def demo_user():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into auth.users (id, email, role, aud, created_at, updated_at)"
            " values (%s,%s,'authenticated','authenticated',now(),now())",
            (user, f"know-{user[:8]}@test.internal"),
        )
        conn.commit()
    yield user
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where created_by=%s", (user,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def _count(sql: str, org_id: str) -> int:
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(sql, (org_id,))
        return cur.fetchone()[0]


def test_seed_knowledge_populates_everything(demo_user):
    base = seed_demo(db_url=DBURL, demo_user_id=demo_user)
    res = seed_knowledge(db_url=DBURL, demo_user_id=demo_user)

    assert not res.get("skipped"), res
    org_a, org_b = base["org_a"], base["org_b"]

    # memoria QA: los 7 kinds en Org A, y contenido propio en Org B
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select distinct kind from public.qa_knowledge where org_id=%s", (org_a,))
        kinds = {r[0] for r in cur.fetchall()}
    assert kinds == ALL_KINDS, f"faltan kinds en org A: {ALL_KINDS - kinds}"
    assert _count("select count(*) from public.qa_knowledge where org_id=%s", org_b) > 0

    # algunos items enlazan a familias reales (alimenta el grafo)
    assert _count(
        "select count(*) from public.qa_knowledge"
        " where org_id=%s and defect_family_id is not null", org_a) > 0

    # causas raíz sobre las 3 familias del seed base (la de test_perfil
    # solo existe tras un push en vivo, que aquí no ocurre)
    assert _count(
        "select count(*) from public.defect_families"
        " where org_id=%s and root_cause is not null", org_a) >= 3

    # calibración viva: una corrección y una etiqueta por familia sembrada
    assert _count("select count(*) from public.triage_corrections where org_id=%s", org_a) >= 3
    assert _count(
        "select count(*) from public.defect_families"
        " where org_id=%s and label is not null and label <> 'unknown'", org_a) >= 3

    # test assets para automation/gaps
    assert _count("select count(*) from public.test_assets where org_id=%s", org_a) >= 3


def test_seed_knowledge_is_idempotent(demo_user):
    seed_demo(db_url=DBURL, demo_user_id=demo_user)
    seed_knowledge(db_url=DBURL, demo_user_id=demo_user)
    res2 = seed_knowledge(db_url=DBURL, demo_user_id=demo_user)
    assert res2.get("skipped"), "la segunda llamada debía saltarse (idempotencia)"


def test_seed_knowledge_requires_base_seed(demo_user):
    res = seed_knowledge(db_url=DBURL, demo_user_id=demo_user)
    assert res.get("skipped") and "seed_demo" in res.get("reason", "")
