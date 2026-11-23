"""Auditoría 2026-11-23 (03-tecnica E8): LLM en caminos calientes y sin tope.
- La narrativa del veredicto se generaba con el LLM en CADA `GET /v2/assurance/run/{id}`.
- El juez del acta hacía una llamada LLM por cada veredicto `llm_assisted`, sin tope."""
import json
import threading

import pytest

from src.ai import judge
from src.ai.judge import (JUDGE_MAX_CALLS, JUDGE_MAX_EVIDENCE_CHARS,
                          JUDGE_MAX_EVIDENCE_ITEMS, compute_ai_eval)
from src.assurance.narrator_cache import NARRATIVE_CACHE_MAX_ENTRIES, CachingNarrator


class _CountingNarrator:
    def __init__(self):
        self.calls = 0

    def summarize(self, verdict):
        self.calls += 1
        return f"narrativa {self.calls}"


def _verdict(**kw):
    base = {"ingested": 3, "known": 1, "novel": 2, "risk": "high",
            "top_families": [{"title": "Timeout", "recurring": True}]}
    return {**base, **kw}


# --- Narrativa cacheada -----------------------------------------------------

def test_narrativa_se_cachea_para_los_mismos_datos():
    inner = _CountingNarrator()
    n = CachingNarrator(inner)
    assert n.summarize(_verdict()) == n.summarize(_verdict()) == "narrativa 1"
    assert inner.calls == 1


def test_narrativa_se_regenera_si_cambian_los_datos():
    inner = _CountingNarrator()
    n = CachingNarrator(inner)
    n.summarize(_verdict())
    n.summarize(_verdict(novel=5))
    assert inner.calls == 2


def test_los_fallos_del_llm_no_se_cachean():
    class _Flaky:
        calls = 0

        def summarize(self, verdict):
            type(self).calls += 1
            if type(self).calls == 1:
                raise RuntimeError("429")
            return "ok"

    n = CachingNarrator(_Flaky())
    with pytest.raises(RuntimeError):
        n.summarize(_verdict())
    assert n.summarize(_verdict()) == "ok"


def test_la_cache_esta_acotada():
    inner = _CountingNarrator()
    n = CachingNarrator(inner, max_entries=2)
    for novel in (1, 2, 3):
        n.summarize(_verdict(novel=novel))
    n.summarize(_verdict(novel=1))          # expulsado: se vuelve a generar
    assert inner.calls == 4
    assert NARRATIVE_CACHE_MAX_ENTRIES >= 1


def test_la_cache_es_thread_safe():
    inner = _CountingNarrator()
    n = CachingNarrator(inner)
    threads = [threading.Thread(target=n.summarize, args=(_verdict(),)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert n.summarize(_verdict()).startswith("narrativa")


def test_get_narrator_devuelve_la_version_cacheada(monkeypatch):
    import src.api_v2 as api_v2
    monkeypatch.setattr(api_v2, "_narrator", None)
    monkeypatch.setattr(api_v2, "_llm_provider_or_none", lambda: None)
    assert isinstance(api_v2.get_narrator(), CachingNarrator)


# --- Tope del juez ----------------------------------------------------------

class _CountingProvider:
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def complete(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        return '{"faithfulness": 0.5, "groundedness": 0.5}'


def _llm_verdicts(n, evidence=None):
    return [{"category": "real", "llm_assisted": True, "rule_applied": "R6_ambiguous",
             "evidence_bundle": evidence if evidence is not None else {"i": i}} for i in range(n)]


def test_el_juez_tiene_tope_de_llamadas():
    prov = _CountingProvider()
    out = compute_ai_eval(verdicts=_llm_verdicts(150), created_at="t", provider=prov)
    assert prov.calls == JUDGE_MAX_CALLS
    assert out["n"] == JUDGE_MAX_CALLS
    assert out["sampled_from"] == 150


def test_sin_muestreo_sampled_from_igual_a_n():
    out = compute_ai_eval(verdicts=_llm_verdicts(2), created_at="t", provider=_CountingProvider())
    assert out["n"] == 2 and out["sampled_from"] == 2


def test_el_juez_acota_el_tamano_de_la_evidencia():
    huge = {f"k{i}": "x" * (JUDGE_MAX_EVIDENCE_CHARS * 3) for i in range(JUDGE_MAX_EVIDENCE_ITEMS + 5)}
    prov = _CountingProvider()
    compute_ai_eval(verdicts=_llm_verdicts(1, evidence=huge), created_at="t", provider=prov)
    prompt = prov.prompts[0]
    assert len(prompt) < (JUDGE_MAX_EVIDENCE_ITEMS + 2) * (JUDGE_MAX_EVIDENCE_CHARS + 200) + 2000
    assert f"k{JUDGE_MAX_EVIDENCE_ITEMS + 1}" not in prompt


def test_constantes_razonables():
    assert 1 <= JUDGE_MAX_CALLS <= 20
    assert judge.JUDGE_MAX_EVIDENCE_CHARS > 0


def test_evidencia_sigue_siendo_json():
    prov = _CountingProvider()
    compute_ai_eval(verdicts=_llm_verdicts(1, evidence={"lineage": ["a", "b"]}),
                    created_at="t", provider=prov)
    assert json.dumps(["a", "b"]) in prov.prompts[0]
