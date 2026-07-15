"""B3 — ingest_run idempotente por (org_id, run_uid), como ingest_ci_run.

El doble upload del mismo reporte NO debe crear un segundo run ni doblar
occurrence_count de las familias (corrompía calibración y lineage).
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def org():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"repdedup-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("repdedup-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def _item(fp: str) -> IngestItem:
    rec = FailureRecord(test_name="t1", error_type="AssertionError", message="boom",
                        trace=None, project="web", source="junit")
    return IngestItem(rec=rec, fingerprint=fp, embedding=[0.1] * 384)


def test_same_run_uid_dedups_and_does_not_double_count(org):
    repo = AssuranceRepository(DBURL)
    ruid = "report:web:" + uuid.uuid4().hex
    fp = "fp-" + uuid.uuid4().hex
    args = dict(user_id=org["user_id"], org_id=org["org_id"], project="web",
                source="junit", items=[_item(fp)], run_uid=ruid)

    first = repo.ingest_run(**args)
    second = repo.ingest_run(**args)  # mismo archivo re-subido — NO debe crear otro run

    assert second["deduplicated"] is True
    assert second["run_id"] == first["run_id"]
    assert second["ingested"] == 1  # summary del run original, no de una re-ingesta

    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select occurrence_count from public.defect_families"
                        " where org_id = %s and signature = %s", (org["org_id"], fp))
            assert cur.fetchone()[0] == 1  # el doble upload NO dobla el contador
            cur.execute("select count(*) from public.failures f"
                        " join public.test_runs r on r.id = f.run_id"
                        " where r.org_id = %s", (org["org_id"],))
            assert cur.fetchone()[0] == 1


def test_without_run_uid_keeps_legacy_behaviour(org):
    repo = AssuranceRepository(DBURL)
    fp = "fp-" + uuid.uuid4().hex
    args = dict(user_id=org["user_id"], org_id=org["org_id"], project="web",
                source="junit", items=[_item(fp)])

    first = repo.ingest_run(**args)
    second = repo.ingest_run(**args)  # sin run_uid: cada llamada crea run (camino legacy)

    assert first["run_id"] != second["run_id"]
    assert second.get("deduplicated", False) is False
