"""Repo del import: upsert por ref externa (dedupe parcial + xmax), get por id,
tope horario y whitelist del refine. Mock-cursor: valida el SQL emitido."""
from unittest.mock import MagicMock

import pytest

from src.knowledge.proposal_repository import KnowledgeProposalRepository


def _repo_with_cursor():
    repo = KnowledgeProposalRepository(
        db_url="postgresql://x", embedder=MagicMock(embed=lambda t: [0.0] * 384))
    cur = MagicMock()
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    repo._connect = MagicMock(return_value=conn)
    return repo, cur


def _member(cur, ok=True):
    """El primer fetchone es el check de membership."""
    cur.fetchone.side_effect = [{"ok": ok}]


def test_upsert_import_sql_dedupe_parcial_y_xmax():
    repo, cur = _repo_with_cursor()
    _member(cur)
    cur.fetchall.return_value = []
    repo.upsert_import_proposal(
        user_id="u1", org_id="o1", created_by="u1", source="jira",
        external_ref="jira:PAY-1", external_url="https://a.atlassian.net/browse/PAY-1",
        project="PAY", kind="leccion", title="T", challenge=None, approach=None,
        domain=None, outcome=None, tags=["PAY"])
    sql = cur.execute.call_args_list[-1].args[0]
    assert "on conflict (org_id, external_ref) where external_ref is not null" in sql
    assert "(xmax = 0) as created" in sql
    assert "imported_at" in sql            # se sella en insert Y en el DO UPDATE
    assert "where knowledge_proposals.status='pending'" in sql


def test_upsert_import_devuelve_created_del_xmax():
    repo, cur = _repo_with_cursor()
    _member(cur)
    cur.fetchall.return_value = [
        {"id": "p1", "org_id": "o1", "defect_family_id": None, "run_id": None,
         "kind": "leccion", "title": "T", "challenge": None, "approach": None,
         "domain": None, "outcome": None, "tags": ["PAY"], "status": "pending",
         "created_at": None, "source": "jira", "external_ref": "jira:PAY-1",
         "external_url": "u", "project": "PAY", "created": True}]
    row = repo.upsert_import_proposal(
        user_id="u1", org_id="o1", created_by="u1", source="jira",
        external_ref="jira:PAY-1", external_url="u", project="PAY", kind="leccion",
        title="T", challenge=None, approach=None, domain=None, outcome=None, tags=[])
    assert row["created"] is True
    assert row["defect_family_id"] is None


def test_upsert_import_no_miembro_none():
    repo, cur = _repo_with_cursor()
    _member(cur, ok=False)
    assert repo.upsert_import_proposal(
        user_id="u1", org_id="o1", created_by="u1", source="jira",
        external_ref="jira:PAY-1", external_url="u", project=None, kind="leccion",
        title="T", challenge=None, approach=None, domain=None, outcome=None,
        tags=[]) is None


def test_get_proposal_exige_membership_en_sql():
    repo, cur = _repo_with_cursor()
    cur.fetchall.return_value = []
    assert repo.get_proposal(user_id="u1", proposal_id="p1") is None
    sql = cur.execute.call_args.args[0]
    assert "memberships" in sql


def test_count_recent_imports_usa_interval():
    repo, cur = _repo_with_cursor()
    _member(cur)
    cur.fetchone.side_effect = [{"ok": True}, {"n": 7}]
    assert repo.count_recent_imports(user_id="u1", org_id="o1") == 7
    sql = cur.execute.call_args.args[0]
    assert "interval '1 hour'" in sql
    assert "imported_at" in sql


def test_update_pending_fields_whitelist():
    repo, cur = _repo_with_cursor()
    with pytest.raises(ValueError):
        repo.update_pending_fields(user_id="u1", proposal_id="p1",
                                   fields={"status": "approved"})


def test_update_pending_fields_solo_pending():
    repo, cur = _repo_with_cursor()
    cur.fetchall.return_value = []
    out = repo.update_pending_fields(user_id="u1", proposal_id="p1",
                                    fields={"title": "Nuevo"})
    assert out is None
    sql = cur.execute.call_args.args[0]
    assert "status='pending'" in sql
    assert "memberships" in sql
