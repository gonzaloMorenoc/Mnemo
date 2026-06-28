"""
RLS behavioural tests for test_assets.

All tests require DATABASE_URL (real prod DB) → marker integration.
Mirrors the pattern of tests/test_qa_knowledge_rls.py.
"""
import os
import uuid

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


# ---------------------------------------------------------------------------
# Schema-level RLS checks
# ---------------------------------------------------------------------------

def test_test_assets_rls_enabled_and_forced():
    """test_assets must have both enable and force row level security active."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select relrowsecurity, relforcerowsecurity from pg_class"
            " where relname = 'test_assets' and relnamespace = 'public'::regnamespace"
        )
        row = cur.fetchone()
    assert row is not None, "tabla test_assets no encontrada en pg_class"
    enabled, forced = row
    assert enabled is True, "test_assets: RLS no habilitada (enable row level security falta)"
    assert forced is True, "test_assets: RLS no forzada (force row level security falta)"


def test_test_assets_member_policy_exists():
    """La policy test_assets_member debe existir en pg_policies."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select policyname from pg_policies"
            " where schemaname = 'public' and tablename = 'test_assets'"
        )
        policies = {r[0] for r in cur.fetchall()}
    assert "test_assets_member" in policies, (
        f"policy test_assets_member no encontrada; políticas actuales: {policies}"
    )


# ---------------------------------------------------------------------------
# Behavioural RLS: non-member cannot see another org's rows
# ---------------------------------------------------------------------------

@pytest.fixture
def two_orgs_setup():
    """
    Create two independent users/orgs, each with one test_asset row.
    Uses BYPASS RLS (superuser connection) to insert directly.
    Yields {org_a, user_a, org_b, user_b, asset_a_id, asset_b_id}.
    Cleans up after test.
    """
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")

    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())

    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        # Create users
        for uid, suffix in [(user_a, "rls-a"), (user_b, "rls-b")]:
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s,%s,'authenticated','authenticated',now(),now())",
                (uid, f"ta-{suffix}-{uid[:6]}@test.internal"),
            )

        # Create orgs (trigger adds creator to memberships)
        cur.execute(
            "insert into public.organizations (name, created_by) values (%s,%s) returning id",
            (f"ta-rls-org-a-{user_a[:6]}", user_a),
        )
        org_a = str(cur.fetchone()[0])

        cur.execute(
            "insert into public.organizations (name, created_by) values (%s,%s) returning id",
            (f"ta-rls-org-b-{user_b[:6]}", user_b),
        )
        org_b = str(cur.fetchone()[0])

        # Insert one test_asset per org directly (superuser bypasses RLS)
        cur.execute(
            "insert into public.test_assets"
            " (org_id, repo_full_name, path, content)"
            " values (%s,'org/repo','test_a.py','content a') returning id",
            (org_a,),
        )
        asset_a_id = str(cur.fetchone()[0])

        cur.execute(
            "insert into public.test_assets"
            " (org_id, repo_full_name, path, content)"
            " values (%s,'org/repo','test_b.py','content b') returning id",
            (org_b,),
        )
        asset_b_id = str(cur.fetchone()[0])

        conn.commit()

    yield {
        "org_a": org_a, "user_a": user_a,
        "org_b": org_b, "user_b": user_b,
        "asset_a_id": asset_a_id, "asset_b_id": asset_b_id,
    }

    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.test_assets where org_id in (%s,%s)", (org_a, org_b))
        cur.execute("delete from public.organizations where id in (%s,%s)", (org_a, org_b))
        cur.execute("delete from auth.users where id in (%s,%s)", (user_a, user_b))
        conn.commit()


def test_non_member_cannot_see_other_org_rows(two_orgs_setup):
    """
    user_a is member of org_a only.
    Querying test_assets for org_b via the repository layer returns [].
    """
    from src.repo_ingest.repository import TestAssetRepository

    class FakeEmb:
        def embed(self, text):
            return [0.1] * 384

    s = two_orgs_setup
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())

    # user_a cannot list org_b's assets
    result = repo.list_assets(user_id=s["user_a"], org_id=s["org_b"])
    assert result == [], "non-member should get [] from list_assets"


def test_non_member_search_returns_empty(two_orgs_setup):
    """user_a cannot search org_b's assets via search_semantic."""
    from src.repo_ingest.repository import TestAssetRepository

    class FakeEmb:
        def embed(self, text):
            return [0.1] * 384

    s = two_orgs_setup
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())

    result = repo.search_semantic(
        user_id=s["user_a"], org_id=s["org_b"], query_embedding=[0.1] * 384
    )
    assert result == [], "non-member should get [] from search_semantic"


def test_member_can_see_own_org_rows(two_orgs_setup):
    """user_a IS a member of org_a and should see its own asset."""
    from src.repo_ingest.repository import TestAssetRepository

    class FakeEmb:
        def embed(self, text):
            return [0.1] * 384

    s = two_orgs_setup
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())

    result = repo.list_assets(user_id=s["user_a"], org_id=s["org_a"])
    ids = [str(r["id"]) for r in result]
    assert s["asset_a_id"] in ids, "member should see their own org's asset"
    assert s["asset_b_id"] not in ids, "member must NOT see a different org's asset"
