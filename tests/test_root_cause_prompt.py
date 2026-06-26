from src.assurance.root_cause import build_root_cause_prompt, build_root_cause_context, _top_frame


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
    # new format: JSON schema prompt (no longer markdown section headers in prompt)
    assert "root_cause" in prompt and "suggested_fix_steps" in prompt


def test_prompt_truncates_to_six_failures():
    fam = {"title": "X", "occurrence_count": 99}
    # sampling happens in context, not in the prompt text directly;
    # verify context has at most _MAX_FAILURES entries (6)
    ctx = build_root_cause_context(fam, _failures(20))
    failure_entries = [c for c in ctx if c["id"].startswith("failure:")]
    assert len(failure_entries) == 6


def test_prompt_marks_user_data_untrusted():
    fam = {"title": "X", "occurrence_count": 1}
    prompt = build_root_cause_prompt(fam, [{"test_name": "t", "error_type": "E",
        "message": "boom", "trace": "at A.java:1", "project": "p"}])
    # new format: untrusted data warning still present (different phrasing)
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
    # spread sampling is now in build_root_cause_context
    ctx = build_root_cause_context(fam, failures)
    failure_entries = [c for c in ctx if c["id"].startswith("failure:")]
    ids_in_ctx = {c["id"] for c in failure_entries}
    assert "failure:t0" in ids_in_ctx
    # at least one from the tail
    assert any(f"failure:t1{d}" in ids_in_ctx for d in "56789")
    assert len(failure_entries) == 6
