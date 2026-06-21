from src.assurance.root_cause import build_root_cause_prompt


def _failures(n):
    return [{"test_name": f"t{i}", "error_type": "TimeoutException",
             "message": f"esperando elemento {i}", "trace": f"at Foo.java:{i}",
             "project": "proj-a" if i % 2 else "proj-b"} for i in range(n)]


def test_prompt_includes_family_and_samples():
    fam = {"title": "Timeout de login", "occurrence_count": 12}
    prompt = build_root_cause_prompt(fam, _failures(3))
    assert "Timeout de login" in prompt
    assert "12" in prompt
    assert "proj-a" in prompt and "proj-b" in prompt
    assert "## Causa raíz" in prompt and "## Pasos sugeridos" in prompt


def test_prompt_truncates_to_six_failures():
    fam = {"title": "X", "occurrence_count": 99}
    prompt = build_root_cause_prompt(fam, _failures(20))
    assert prompt.count("- test=") == 6


def test_prompt_marks_user_data_untrusted():
    fam = {"title": "X", "occurrence_count": 1}
    prompt = build_root_cause_prompt(fam, [{"test_name": "t", "error_type": "E",
        "message": "boom", "trace": "at A.java:1", "project": "p"}])
    assert "<<<DATA>>>" in prompt and "<<<END_DATA>>>" in prompt
    assert "no confiables" in prompt.lower() or "no confiable" in prompt.lower()
