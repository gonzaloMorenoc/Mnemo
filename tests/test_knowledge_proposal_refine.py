"""Refine por-propuesta: UNA llamada LLM que condensa y propone kind/domain.
Si el LLM cae → None (503 en el endpoint) y la propuesta NO se toca."""
from unittest.mock import MagicMock, patch

from src.knowledge.proposal_service import KnowledgeProposalService


def _svc(proposal="default"):
    repo = MagicMock()
    if proposal == "default":
        proposal = {
            "id": "p1", "status": "pending", "kind": "leccion",
            "title": "Cobro duplicado", "challenge": "texto largo…", "approach": None,
            "domain": None, "outcome": "Resolución: Fixed", "tags": ["PAY"],
            "source": "jira"}
    repo.get_proposal.return_value = proposal
    repo.update_pending_fields.return_value = {"id": "p1", "title": "Mejor título"}
    svc = KnowledgeProposalService(repo=repo, assurance_repo=MagicMock(),
                                   analyzer=MagicMock())
    return svc, repo


def test_refine_actualiza_con_la_salida_del_llm():
    svc, repo = _svc()
    llm_out = {"title": "Mejor título", "challenge": "c", "approach": "a",
               "outcome": "o", "kind": "regla_negocio", "domain": "pagos"}
    with patch("src.knowledge.proposal_service.generate_structured",
               return_value=llm_out):
        out = svc.refine(user_id="u1", proposal_id="p1")
    assert out == {"id": "p1", "title": "Mejor título"}
    fields = repo.update_pending_fields.call_args.kwargs["fields"]
    assert fields["kind"] == "regla_negocio"
    assert fields["domain"] == "pagos"
    assert fields["title"] == "Mejor título"


def test_refine_llm_caido_no_toca_nada():
    svc, repo = _svc()
    with patch("src.knowledge.proposal_service.generate_structured",
               return_value=None):
        assert svc.refine(user_id="u1", proposal_id="p1") is None
    repo.update_pending_fields.assert_not_called()


def test_refine_titulo_vacio_del_llm_no_toca_nada():
    svc, repo = _svc()
    llm_out = {"title": "  ", "challenge": "c", "approach": "a", "outcome": "o",
               "kind": "leccion", "domain": ""}
    with patch("src.knowledge.proposal_service.generate_structured",
               return_value=llm_out):
        assert svc.refine(user_id="u1", proposal_id="p1") is None
    repo.update_pending_fields.assert_not_called()


def test_refine_kind_invalido_del_llm_se_descarta():
    svc, repo = _svc()
    llm_out = {"title": "T", "challenge": "", "approach": "", "outcome": "",
               "kind": "categoria_inventada", "domain": ""}
    with patch("src.knowledge.proposal_service.generate_structured",
               return_value=llm_out):
        svc.refine(user_id="u1", proposal_id="p1")
    fields = repo.update_pending_fields.call_args.kwargs["fields"]
    assert "kind" not in fields          # kind inválido → conservar el actual


def test_refine_conserva_campos_que_el_llm_deja_vacios():
    svc, repo = _svc()
    llm_out = {"title": "T", "challenge": "", "approach": "", "outcome": "",
               "kind": "", "domain": ""}
    with patch("src.knowledge.proposal_service.generate_structured",
               return_value=llm_out):
        svc.refine(user_id="u1", proposal_id="p1")
    fields = repo.update_pending_fields.call_args.kwargs["fields"]
    assert fields["challenge"] == "texto largo…"        # se conserva el existente
    assert fields["outcome"] == "Resolución: Fixed"


def test_refine_propuesta_inexistente_o_no_pendiente():
    svc, repo = _svc(proposal=None)
    assert svc.refine(user_id="u1", proposal_id="nope") is None
    svc2, _ = _svc(proposal={"id": "p1", "status": "approved", "kind": "leccion",
                             "title": "T", "challenge": None, "approach": None,
                             "domain": None, "outcome": None, "tags": [],
                             "source": "jira"})
    assert svc2.refine(user_id="u1", proposal_id="p1") is None


def test_refine_prompt_en_espanol_y_con_kinds():
    svc, repo = _svc()
    with patch("src.knowledge.proposal_service.generate_structured",
               return_value=None) as gen:
        svc.refine(user_id="u1", proposal_id="p1")
    prompt = gen.call_args.kwargs["prompt"]
    assert "español" in prompt
    assert "regla_negocio" in prompt      # enumera los kinds
    assert "Cobro duplicado" in prompt    # incluye la propuesta actual
