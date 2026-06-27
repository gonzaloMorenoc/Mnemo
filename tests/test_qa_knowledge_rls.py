import os

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

DBURL = os.getenv("DATABASE_URL", "")


def _connect():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return psycopg.connect(DBURL)


def test_qa_knowledge_rls_enabled_and_forced():
    """qa_knowledge must have both enable and force row level security active."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select relrowsecurity, relforcerowsecurity from pg_class"
            " where relname = 'qa_knowledge' and relnamespace = 'public'::regnamespace"
        )
        row = cur.fetchone()
    assert row is not None, "tabla qa_knowledge no encontrada en pg_class"
    enabled, forced = row
    assert enabled is True, "qa_knowledge: RLS no habilitada (enable row level security falta)"
    assert forced is True, "qa_knowledge: RLS no forzada (force row level security falta)"


def test_qa_knowledge_member_policy_exists():
    """La policy qa_knowledge_member debe existir en pg_policies."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select policyname from pg_policies"
            " where schemaname = 'public' and tablename = 'qa_knowledge'"
        )
        policies = {r[0] for r in cur.fetchall()}
    assert "qa_knowledge_member" in policies, (
        f"policy qa_knowledge_member no encontrada; políticas actuales: {policies}"
    )
