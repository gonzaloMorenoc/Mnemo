"""El approve de una propuesta hereda el `project` del run que destapó la familia."""
from unittest.mock import MagicMock, patch

from src.knowledge.proposal_repository import KnowledgeProposalRepository


def _fake_pool(cur):
    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


def _repo():
    embedder = MagicMock()
    embedder.embed.return_value = [0.0] * 384
    return KnowledgeProposalRepository(db_url="postgres://x", embedder=embedder)


def _approve(repo, cur):
    with patch("src.knowledge.proposal_repository.get_pool", return_value=_fake_pool(cur)):
        with patch("src.knowledge.proposal_repository.insert_qa_knowledge",
                   return_value={"id": "k1"}) as ins:
            out = repo.approve(user_id="u", proposal_id="p", kind="leccion", title="T",
                               challenge=None, approach=None, domain=None, outcome=None,
                               tags=[])
    return out, ins


def test_approve_inherits_project_from_run():
    repo = _repo()
    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"org_id": "o1", "defect_family_id": "f1", "run_id": "r1",
         "source": "auto_triage", "external_url": None, "project": None},  # CAS returning
        {"project": "checkout-suite"},                                # lookup en test_runs
    ]
    out, ins = _approve(repo, cur)
    assert out == {"id": "k1"}
    assert ins.call_args.kwargs["project"] == "checkout-suite"
    sql = " ".join(str(c.args[0]) for c in cur.execute.call_args_list)
    assert "from public.test_runs" in sql


def test_approve_without_run_leaves_project_none():
    repo = _repo()
    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"org_id": "o1", "defect_family_id": "f1", "run_id": None,
         "source": "auto_triage", "external_url": None, "project": None},
    ]
    out, ins = _approve(repo, cur)
    assert out == {"id": "k1"}
    assert ins.call_args.kwargs["project"] is None
    # sin run no hay lookup extra
    assert cur.execute.call_count == 1
