from src.assurance.root_cause import RootCauseAnalyzer, build_root_cause_context


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _Boom:
    def complete(self, prompt): raise RuntimeError("llm down")


_FAMILY = {"title": "checkout falla", "occurrence_count": 5}
_FAILURES = [{"id": "fl1", "test_name": "t_checkout", "error_type": "AssertionError",
              "message": "expected 200 got 500", "trace": "at checkout.ts:42", "project": "alpha"}]


def test_context_includes_failures_and_lineage_with_ids():
    ctx = build_root_cause_context(_FAMILY, _FAILURES, lineage=["beta", "gamma"])
    ids = {c["id"] for c in ctx}
    assert any(i.startswith("failure:") for i in ids)
    assert any(i.startswith("lineage") for i in ids)   # el linaje cross-proyecto es evidencia citable


def test_analyze_structured_returns_schema_and_citations():
    out = '{"root_cause":"500 del backend","why_it_happened":"deploy roto","how_to_fix":"revertir","suggested_fix_steps":["rollback"],"confidence":0.8,"citations":["failure:fl1"]}'
    analyzer = RootCauseAnalyzer(_Provider(out))
    res = analyzer.analyze_structured(_FAMILY, _FAILURES, lineage=["beta"])
    assert res["root_cause"] == "500 del backend"
    assert res["citations"] == ["failure:fl1"] and res["confidence"] == 0.8


def test_analyze_structured_degrades_without_llm():
    analyzer = RootCauseAnalyzer(_Boom())
    res = analyzer.analyze_structured(_FAMILY, _FAILURES)
    assert res["root_cause"]   # fallback no vacío
    assert res["citations"] == [] and res["confidence"] == 0.0


def test_analyze_str_is_markdown_with_lineage_and_citations():
    out = '{"root_cause":"500","why_it_happened":"x","how_to_fix":"y","suggested_fix_steps":["a"],"confidence":0.8,"citations":["failure:fl1"]}'
    md = RootCauseAnalyzer(_Provider(out)).analyze(_FAMILY, _FAILURES, lineage=["beta"])
    assert "## Causa raíz" in md and "500" in md
    assert "beta" in md            # linaje visible
    assert "failure:fl1" in md     # citas visibles


def test_analyze_str_backward_compatible_signature():
    # la interfaz vieja (sin lineage) sigue devolviendo str
    md = RootCauseAnalyzer(_Provider('{"root_cause":"z"}')).analyze(_FAMILY, _FAILURES)
    assert isinstance(md, str) and "z" in md
