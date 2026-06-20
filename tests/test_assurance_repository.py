import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from src.ingest.models import FailureRecord
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem

DBURL = os.getenv("DATABASE_URL", "")


def _emb(seed: float):
    return [seed] + [0.0] * 383


def _emb_at(pos: int, val: float = 1.0):
    """Return a unit vector with val at position pos and zeros elsewhere.

    Two calls with different pos values produce orthogonal vectors (cosine = 0),
    guaranteeing that decide_match creates separate defect families.
    """
    v = [0.0] * 384
    v[pos] = val
    return v


def _emb_two(p1: int, v1: float, p2: int, v2: float):
    """Return a vector with two non-zero components (for crafting near/far neighbours)."""
    v = [0.0] * 384
    v[p1] = v1
    v[p2] = v2
    return v


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org(repo):
    user_id = str(uuid.uuid4())
    email = f"test-{user_id[:8]}@test.internal"
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            # Create a real auth.users row so FK constraints are satisfied
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (user_id, email),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("test-org-" + user_id[:8], user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def _item(project, msg, trace, seed):
    rec = FailureRecord(
        test_name="t",
        error_type="TimeoutException",
        message=msg,
        trace=trace,
        project=project,
        source="allure",
    )
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_ingest_groups_same_error_across_projects(repo, org):
    u, o = org["user_id"], org["org_id"]
    r1 = repo.ingest_run(
        user_id=u,
        org_id=o,
        project="proj-a",
        source="allure",
        items=[_item("proj-a", "TimeoutException after 100ms", "at A.java:1", 1.0)],
    )
    r2 = repo.ingest_run(
        user_id=u,
        org_id=o,
        project="proj-b",
        source="allure",
        items=[_item("proj-b", "TimeoutException after 999ms", "at A.java:2", 1.0)],
    )
    assert r1["known"] == 0 and r1["novel"] == 1
    assert r2["known"] == 1 and r2["novel"] == 0
    defects = repo.list_defects(user_id=u, org_id=o)
    assert len(defects) == 1
    assert defects[0]["occurrence_count"] == 2
    lineage = repo.get_lineage(user_id=u, defect_id=defects[0]["id"])
    projects = {f["project"] for f in lineage["failures"]}
    assert projects == {"proj-a", "proj-b"}


def test_isolation_between_orgs(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.ingest_run(
        user_id=u,
        org_id=o,
        project="p",
        source="allure",
        items=[_item("p", "UniqueError xyz", None, 0.5)],
    )
    other_user = str(uuid.uuid4())
    assert repo.list_defects(user_id=other_user, org_id=o) == []


def test_ingest_run_rejects_non_member(repo, org):
    other_user = str(uuid.uuid4())
    with pytest.raises(PermissionError):
        repo.ingest_run(user_id=other_user, org_id=org["org_id"], project="p", source="allure",
                        items=[_item("p", "X", None, 0.3)])


def test_get_run_assurance_data(repo, org):
    u, o = org["user_id"], org["org_id"]
    # Use orthogonal embeddings (different dimensions) so decide_match creates
    # two separate defect families (cosine similarity == 0 between them).
    rec_a = FailureRecord(test_name="t", error_type="TimeoutException",
                          message="TimeoutException at host 10.0.0.1", trace="at A.java:1",
                          project="proj-a", source="allure")
    rec_b = FailureRecord(test_name="t", error_type="NullPointerException",
                          message="NullPointer somewhere", trace="at B.java:2",
                          project="proj-a", source="allure")
    item_a = IngestItem(rec=rec_a, fingerprint=fingerprint(rec_a), embedding=_emb_at(0))
    item_b = IngestItem(rec=rec_b, fingerprint=fingerprint(rec_b), embedding=_emb_at(1))
    out = repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure",
                          items=[item_a, item_b])
    run_id = out["run_id"]
    data = repo.get_run_assurance_data(user_id=u, run_id=run_id)
    assert data["run"] is not None
    assert data["summary"]["ingested"] == 2
    assert len(data["families"]) == 2
    for fam in data["families"]:
        assert fam["run_count"] >= 1 and "occurrence_count" in fam and "title" in fam


def test_get_run_assurance_data_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="p", source="allure",
                          items=[_item("p", "X error", None, 0.3)])
    other = str(uuid.uuid4())
    data = repo.get_run_assurance_data(user_id=other, run_id=out["run_id"])
    assert data["run"] is None


def test_exact_signature_match_survives_centroid_drift(repo, org):
    """Regresion C1: una familia con firma exacta debe emparejarse aunque su
    centroide haya derivado fuera del top-K por coseno.

    Escenario: se crea la familia objetivo F, luego 11 familias senuelo cuyos
    centroides estan mas cerca (coseno) del embedding de re-ingesta que el de F,
    empujando a F fuera del top-10. Sin el fix de _query_candidates (UNION por
    firma) se crearia una familia DUPLICADA con la misma firma; con el fix, F se
    incluye siempre como candidato y el match exacto la reutiliza.
    """
    u, o = org["user_id"], org["org_id"]

    # 1) Familia objetivo F: centroide ortogonal (posicion 383) al vector de re-ingesta.
    rec_f = FailureRecord(test_name="t", error_type="TargetException",
                          message="TargetException drift sentinel", trace="at T.java:1",
                          project="proj-a", source="allure")
    sig_f = fingerprint(rec_f)
    repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure",
                    items=[IngestItem(rec=rec_f, fingerprint=sig_f, embedding=_emb_at(383))])

    # 2) 11 familias senuelo, cada una mas cercana (coseno) a E=_emb_at(0) que F.
    #    Usamos LETRAS distintas (no numeros, que normalize() colapsa a <n>) para
    #    que cada senuelo tenga una firma unica.
    letters = "BCDEFGHIJKL"
    for i in range(1, 12):
        rec_d = FailureRecord(test_name="t", error_type="DecoyException",
                              message=f"DecoyException kind {letters[i - 1]} occurred",
                              trace="at D.java:1", project="proj-a", source="allure")
        repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure",
                        items=[IngestItem(rec=rec_d, fingerprint=fingerprint(rec_d),
                                          embedding=_emb_two(0, 0.5, i, 1.0))])

    # 3) Re-ingerir la MISMA firma que F con un embedding disimilar a su centroide.
    rec_f2 = FailureRecord(test_name="t2", error_type="TargetException",
                           message="TargetException drift sentinel", trace="at T.java:99",
                           project="proj-b", source="allure")
    assert fingerprint(rec_f2) == sig_f  # misma firma que F
    repo.ingest_run(user_id=u, org_id=o, project="proj-b", source="allure",
                    items=[IngestItem(rec=rec_f2, fingerprint=sig_f, embedding=_emb_at(0))])

    # 4) Debe haber exactamente UNA familia con la firma de F (no un duplicado):
    #    F (occurrence_count == 2) + 11 senuelos (occurrence_count == 1) = 12 familias.
    defects = repo.list_defects(user_id=u, org_id=o)
    assert len(defects) == 12
    matched = [d for d in defects if d["occurrence_count"] == 2]
    assert len(matched) == 1
