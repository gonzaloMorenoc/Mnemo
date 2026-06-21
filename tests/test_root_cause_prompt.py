from src.assurance.root_cause import build_root_cause_prompt, _top_frame


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


def test_top_frame_skips_framework_internals():
    trace = ("at org.testng.Assert.fail(Assert.java:96)\n"
             "at org.junit.Assert.assertEquals(Assert.java:115)\n"
             "at com.example.LoginTest.testLogin(LoginTest.java:45)")
    assert _top_frame(trace) == "at com.example.LoginTest.testLogin(LoginTest.java:45)"


def test_top_frame_falls_back_to_first_if_all_internal():
    trace = "at org.testng.Assert.fail(Assert.java:96)"
    assert _top_frame(trace) == "at org.testng.Assert.fail(Assert.java:96)"


def test_sample_spreads_across_failures():
    fam = {"title": "X", "occurrence_count": 99}
    failures = [{"test_name": f"t{i}", "error_type": "E", "message": f"m{i}",
                 "trace": "at A.java:1", "project": "p"} for i in range(20)]
    prompt = build_root_cause_prompt(fam, failures)
    # spread sampling includes a late failure (e.g. t19/t1x), not just t0..t5
    assert "test=t0" in prompt
    assert any(f"test=t1{d}" in prompt for d in "56789")  # at least one from the tail
    assert prompt.count("- test=") == 6
