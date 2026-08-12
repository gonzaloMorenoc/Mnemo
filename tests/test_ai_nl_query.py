from src.ai.nl_query import answer_question


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _Boom:
    def complete(self, prompt): raise RuntimeError("llm down")


_FAMS = [{"family_id": "fam1", "title": "checkout 500", "label": "real", "occurrence_count": 3, "root_cause": "backend 500"},
         {"family_id": "fam2", "title": "login timeout", "label": "flaky", "occurrence_count": 1, "root_cause": None}]


def test_answer_with_citations():
    prov = _Provider('{"answer":"Checkout falla por un 500 del backend.","citations":["fam1"]}')
    res = answer_question(question="¿qué rompe checkout?", families=_FAMS, provider=prov)
    assert "500" in res["answer"] and res["citations"] == ["fam1"]


def test_no_families_returns_empty_answer():
    res = answer_question(question="¿algo?", families=[], provider=_Provider("{}"))
    assert res["citations"] == [] and res["answer"]   # mensaje de "no hay datos"


def test_degrades_without_llm_to_relevant_families():
    res = answer_question(question="¿qué rompe checkout?", families=_FAMS, provider=_Boom())
    assert "checkout 500" in res["answer"]          # devuelve las familias relevantes
    assert res["citations"] == ["fam1", "fam2"]     # cita las familias encontradas


# ---------------------------------------------------------------------------
# La razón de la etiqueta humana (el "por qué" que escribió el senior) tiene que
# llegar al contexto del LLM: es el conocimiento tácito capturado en el flujo.
# Auditoría 2026-08-12, H1: se guardaba en triage_corrections y nadie la leía.
# ---------------------------------------------------------------------------

class _Spy:
    def __init__(self):
        self.prompt = ""

    def complete(self, prompt):
        self.prompt = prompt
        return '{"answer":"x","citations":[]}'


def test_label_reason_reaches_the_llm_context():
    fams = [{"family_id": "f1", "title": "checkout timeout", "label": "flaky",
             "occurrence_count": 3, "root_cause": None,
             "label_reason": "Timeouts por runners fríos del sandbox del PSP"}]
    spy = _Spy()
    answer_question(question="¿por qué es inestable checkout?", families=fams, provider=spy)
    assert "runners fríos" in spy.prompt


def test_families_without_reason_keep_working():
    # Familias antiguas (o sin corrección) no llevan label_reason: nada se rompe.
    spy = _Spy()
    answer_question(question="¿qué rompe checkout?", families=_FAMS, provider=spy)
    assert "razón=" not in spy.prompt
