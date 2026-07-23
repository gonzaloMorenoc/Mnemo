from src.ingest.summary import RunSummary, summarize, to_manifest


def test_junit_summary_de_cabecera():
    xml = b'<testsuite tests="10" failures="2" errors="1" skipped="3"></testsuite>'
    s = summarize("junit", xml)
    assert (s.total, s.failed, s.skipped, s.passed) == (10, 3, 3, 4)  # failed=failures+errors
    assert s.complete is True


def test_testng_summary():
    xml = b'<testng-results total="8" passed="5" failed="2" skipped="1"></testng-results>'
    s = summarize("testng", xml)
    assert (s.total, s.passed, s.failed, s.skipped) == (8, 5, 2, 1) and s.complete


def test_robot_summary_suma_stats():
    xml = b'<robot><statistics><total><stat pass="7" fail="2" skip="1">All</stat></total></statistics></robot>'
    s = summarize("robot", xml)
    assert (s.total, s.passed, s.failed, s.skipped) == (10, 7, 2, 1) and s.complete


def test_cypress_summary_de_stats():
    js = b'{"stats":{"tests":9,"passes":7,"failures":1,"pending":1,"skipped":0},"results":[]}'
    s = summarize("cypress", js)
    assert (s.total, s.passed, s.failed, s.skipped) == (9, 7, 1, 1) and s.complete


def test_playwright_summary_suma_buckets():
    js = b'{"stats":{"expected":5,"unexpected":2,"flaky":1,"skipped":2},"suites":[]}'
    s = summarize("playwright", js)
    assert (s.total, s.passed, s.failed, s.skipped, s.flaky) == (10, 5, 2, 2, 1) and s.complete


def test_allure_summary_cuenta_items():
    js = b'[{"status":"passed"},{"status":"failed"},{"status":"broken"},{"status":"skipped"}]'
    s = summarize("allure", js)
    assert (s.total, s.passed, s.failed, s.skipped) == (4, 1, 2, 1) and s.complete  # failed=failed+broken


def test_cucumber_summary_por_scenario():
    js = (b'[{"elements":[{"steps":[{"result":{"status":"passed"}}]},'
          b'{"steps":[{"result":{"status":"failed"}},{"result":{"status":"skipped"}}]}]}]')
    s = summarize("cucumber", js)
    # 2 scenarios: uno todo passed, otro con un failed → failed
    assert (s.total, s.passed, s.failed) == (2, 1, 1) and s.complete


def test_summary_vacio_no_es_complete():
    xml = b'<testsuite tests="0" failures="0"></testsuite>'
    s = summarize("junit", xml)
    assert s.total == 0 and s.complete is False


def test_summary_formato_desconocido_none():
    assert summarize("desconocido", b"{}") is None


def test_summary_parseo_fallido_none():
    assert summarize("junit", b"no es xml") is None


def test_to_manifest_shape():
    s = RunSummary(total=10, passed=8, failed=2, skipped=0, complete=True, source_format="junit")
    m = to_manifest(s, artifact_sha256="abc", commit_sha="c1")
    assert m == {"total": 10, "passed": 8, "failed": 2, "skipped": 0, "flaky": 0,
                 "complete": True, "source_format": "junit",
                 "artifact_sha256": "abc", "commit_sha": "c1"}


def test_summary_stats_no_dict_devuelve_none():
    # stats presente pero NO-dict → AttributeError NO debe escapar (contrato: None)
    assert summarize("cypress", b'{"stats":[1,2,3],"results":[]}') is None
    assert summarize("playwright", b'{"stats":"oops","suites":[]}') is None


def test_junit_multisuite_sin_agregado_raiz_suma_hijos():
    xml = (b'<testsuites>'
           b'<testsuite tests="10" failures="10"/>'
           b'<testsuite tests="10" skipped="10"/>'
           b'</testsuites>')
    s = summarize("junit", xml)
    assert (s.total, s.failed, s.skipped, s.passed) == (20, 10, 10, 0)


def test_junit_testsuites_con_agregado_raiz_no_dobla():
    xml = b'<testsuites tests="20" failures="2"><testsuite tests="20" failures="2"/></testsuites>'
    s = summarize("junit", xml)
    assert s.total == 20 and s.failed == 2


def test_cucumber_ignora_background():
    js = (b'[{"elements":['
          b'{"type":"background","steps":[{"result":{"status":"passed"}}]},'
          b'{"type":"scenario","steps":[{"result":{"status":"failed"}}]}]}]')
    s = summarize("cucumber", js)
    assert s.total == 1 and s.failed == 1
