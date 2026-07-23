"""Approve de una propuesta IMPORTADA (sin familia): no debe castear None a "None",
debe pasar source/source_url/confidence/project desde la FILA (no del request)."""
from unittest.mock import MagicMock, patch

from src.knowledge.proposal_repository import KnowledgeProposalRepository


def _repo_with_cursor(cas_row):
    repo = KnowledgeProposalRepository(
        db_url="postgresql://x", embedder=MagicMock(embed=lambda t: [0.0] * 384))
    cur = MagicMock()
    cur.fetchone.return_value = cas_row
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    repo._connect = MagicMock(return_value=conn)
    return repo, cur


def test_approve_import_sin_familia_no_castea_none():
    cas_row = {"org_id": "o1", "defect_family_id": None, "run_id": None,
               "source": "jira",
               "external_url": "https://acme.atlassian.net/browse/PAY-1",
               "project": "PAY"}
    repo, cur = _repo_with_cursor(cas_row)
    with patch("src.knowledge.proposal_repository.insert_qa_knowledge") as ins:
        ins.return_value = {"id": "k1"}
        repo.approve(user_id="u1", proposal_id="p1", kind="leccion", title="T",
                     challenge=None, approach=None, domain=None, outcome=None, tags=[])
    kwargs = ins.call_args.kwargs
    assert kwargs["defect_family_id"] is None          # no "None"
    assert kwargs["source"] == "jira"                  # de la fila, no hardcode
    assert kwargs["source_url"] == "https://acme.atlassian.net/browse/PAY-1"
    assert kwargs["confidence"] == "confirmado"        # contenido humano
    assert kwargs["project"] == "PAY"                  # de la columna project


def test_approve_triaje_mantiene_inferido():
    cas_row = {"org_id": "o1", "defect_family_id": "f1", "run_id": None,
               "source": "auto_triage", "external_url": None, "project": None}
    repo, cur = _repo_with_cursor(cas_row)
    with patch("src.knowledge.proposal_repository.insert_qa_knowledge") as ins:
        ins.return_value = {"id": "k1"}
        repo.approve(user_id="u1", proposal_id="p1", kind="leccion", title="T",
                     challenge=None, approach=None, domain=None, outcome=None, tags=[])
    kwargs = ins.call_args.kwargs
    assert kwargs["source"] == "auto_triage"
    assert kwargs["confidence"] == "inferido"
    assert kwargs["defect_family_id"] == "f1"
    assert kwargs["source_url"] is None
