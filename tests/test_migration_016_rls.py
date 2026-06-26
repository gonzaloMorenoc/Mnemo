import os

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

DBURL = os.getenv("DATABASE_URL", "")

_BASE_TABLES = ["profiles", "organizations", "memberships", "documents",
                "chunks", "embeddings", "analyses"]


def _rls_flags():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select relname, relrowsecurity, relforcerowsecurity from pg_class"
            " where relnamespace = 'public'::regnamespace and relkind = 'r'"
            "   and relname = any(%s)", (_BASE_TABLES,))
        return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


def test_base_tables_have_rls_enabled_and_forced():
    flags = _rls_flags()
    for t in _BASE_TABLES:
        assert t in flags, f"tabla {t} no encontrada"
        enabled, forced = flags[t]
        assert enabled is True, f"{t}: RLS no habilitada"
        assert forced is True, f"{t}: RLS no forzada (force row level security falta)"


def test_hardening_indexes_exist():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    expected = {"idx_triage_verdicts_failure", "idx_actions_verdict",
                "idx_triage_corrections_family", "idx_test_runs_commit", "idx_certificates_org"}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select indexname from pg_indexes where schemaname='public' and indexname = any(%s)",
                    (list(expected),))
        found = {r[0] for r in cur.fetchall()}
    assert expected <= found, f"faltan índices: {expected - found}"
