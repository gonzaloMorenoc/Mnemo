import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.demo.seed import seed_demo  # noqa: E402 — import after dotenv

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def demo_user():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into auth.users (id, email, role, aud, created_at, updated_at)"
            " values (%s,%s,'authenticated','authenticated',now(),now())",
            (user, f"demo-{user[:8]}@test.internal"),
        )
        conn.commit()
    yield user
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        # borra las orgs creadas por el seed (created_by = user) → CASCADE; luego el user
        cur.execute("delete from public.organizations where created_by=%s", (user,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


# ---------------------------------------------------------------------------
# Helpers de consulta directa (sin RLS – conexión superuser del pooler)
# ---------------------------------------------------------------------------

def _verdict_categories(org_id: str) -> set:
    """Devuelve el conjunto de categorías de triaje distintas para un org."""
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select distinct tv.category from public.triage_verdicts tv"
            " where tv.org_id = %s",
            (org_id,),
        )
        return {r[0] for r in cur.fetchall()}


def _has_certificates(org_id: str) -> bool:
    """True si existe al menos un certificado para algún run del org."""
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select exists(select 1 from public.certificates where org_id = %s) as ok",
            (org_id,),
        )
        return cur.fetchone()[0]


def _commit_exists(commit_sha: str) -> bool:
    """True si existe algún run con ese commit_sha en la BD."""
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select exists(select 1 from public.test_runs where commit_sha = %s) as ok",
            (commit_sha,),
        )
        return cur.fetchone()[0]


def _org_count(user_id: str) -> int:
    """Número de orgs creadas por un usuario."""
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select count(*) from public.organizations where created_by = %s",
            (user_id,),
        )
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_seed_creates_two_orgs_with_processed_runs(demo_user):
    res = seed_demo(db_url=DBURL, demo_user_id=demo_user)
    assert res["org_a"] and res["org_b"] and res["org_a"] != res["org_b"]
    # Org A: veredictos de las 3 categorias (nucleo del test, siempre verificado)
    cats = _verdict_categories(res["org_a"])
    assert {"flaky", "maintenance", "real"} <= cats, f"faltan categorias: {cats}"
    # Certificados: best-effort (depende de la clave de firma); en el contenedor de demo
    # MNEMO_SIGNING_PRIVATE_KEY esta definida; en CI/local puede estar ausente.
    from src.config import MNEMO_SIGNING_PRIVATE_KEY
    if MNEMO_SIGNING_PRIVATE_KEY:
        assert _has_certificates(res["org_a"]), "clave presente pero no se emitio ningun certificado"
    # el run fresco NO esta ingerido (su commit no aparece en BD)
    assert not _commit_exists("demo-fresh-push"), "fresh_push fue ingerido pero no debia serlo"


def test_seed_is_idempotent(demo_user):
    seed_demo(db_url=DBURL, demo_user_id=demo_user)
    res2 = seed_demo(db_url=DBURL, demo_user_id=demo_user)  # segunda llamada
    assert res2.get("skipped") or _org_count(demo_user) == 2, (
        "la segunda llamada duplico orgs o no reporto skipped"
    )
