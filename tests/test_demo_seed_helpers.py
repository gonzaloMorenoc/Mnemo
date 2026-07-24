from src.ci.models import CiRunArtifact, CiTestResult
from src.demo.seed import _padded, _trend_artifact, _PAD_TOTAL, _FAIL_EXPORT


def _art(tests):
    return CiRunArtifact(project="p", org_id="o", commit_sha="c", source="playwright", tests=tests)


def test_padded_rellena_hasta_total_con_pass_sin_tocar_los_existentes():
    fail = CiTestResult(test_name="test_x", status="fail")
    out = _padded(_art([fail]), total=10)
    assert len(out.tests) == 10
    assert out.tests[0] == fail  # el fallo original se conserva primero
    assert all(t.status == "pass" for t in out.tests[1:])
    assert out.tests[1].test_name.startswith("test_suite_case_")


def test_padded_no_reduce_si_ya_hay_suficientes():
    tests = [CiTestResult(test_name=f"t{i}", status="pass") for i in range(12)]
    out = _padded(_art(tests), total=10)
    assert len(out.tests) == 12


def test_padded_default_total():
    out = _padded(_art([CiTestResult(test_name="t", status="fail")]))
    assert len(out.tests) == _PAD_TOTAL


def test_trend_artifact_compone_pass_mas_fallos():
    art = _trend_artifact(org_id="o", project="p", commit="demo-trend-01", n_pass=38, failures=[_FAIL_EXPORT])
    assert art.org_id == "o" and art.commit_sha == "demo-trend-01"
    assert len(art.tests) == 39
    assert sum(1 for t in art.tests if t.status == "pass") == 38
    assert any(t.test_name == "test_export_csv" and t.status == "fail" for t in art.tests)


def test_trend_artifact_sin_fallos_es_todo_verde():
    art = _trend_artifact(org_id="o", project="p", commit="c", n_pass=5)
    assert len(art.tests) == 5 and all(t.status == "pass" for t in art.tests)
