"""La causa raíz que propone la IA parte de la etiqueta y la razón humanas
(auditoría 23-nov, R5): si María etiquetó la familia como `infra` con «sandbox del
PSP en frío», la propuesta no puede ignorarlo."""
from src.assurance.root_cause import build_root_cause_context, build_root_cause_prompt

_FAILS = [{"test_name": "t", "error_type": "TimeoutError", "message": "socket hang up",
           "trace": "at pay.spec.ts:3", "project": "checkout"}]


def test_prompt_includes_human_label_and_reason():
    fam = {"title": "TimeoutError", "occurrence_count": 4, "label": "infra",
           "label_reason": "sandbox del PSP en frío a primera hora"}
    prompt = build_root_cause_prompt(fam, _FAILS)
    assert "infra" in prompt
    assert "sandbox del PSP en frío a primera hora" in prompt
    assert "coherente" in prompt.lower()


def test_context_carries_the_human_reason_as_citable_evidence():
    fam = {"title": "T", "label": "infra", "label_reason": "sandbox del PSP en frío"}
    ctx = build_root_cause_context(fam, _FAILS)
    human = [c for c in ctx if c["id"] == "human:label"]
    assert human and "sandbox del PSP en frío" in human[0]["content"]


def test_unlabeled_family_adds_no_human_block():
    fam = {"title": "T", "label": "unknown", "label_reason": None}
    assert "Etiqueta humana" not in build_root_cause_prompt(fam, _FAILS)
    assert not [c for c in build_root_cause_context(fam, _FAILS) if c["id"] == "human:label"]


def test_long_reason_is_truncated():
    fam = {"title": "T", "label": "real", "label_reason": "x" * 5000}
    assert "x" * 1001 not in build_root_cause_prompt(fam, _FAILS)
