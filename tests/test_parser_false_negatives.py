"""B1 — los parsers no deben perder fallos de suite/config ni fallos sin mensaje.

Un run rojo cuyos fallos se pierdan → 0 registros → `compute_verdict([]) == "apto"`
→ certificado verde firmado de una release rota. Estos tests fijan el contrato:
capturar fallos a nivel de suite/config, no descartar por mensaje vacío, y una red
de seguridad (la cabecera declara fallos pero se extraen 0 → registro sintético).
Y — igual de importante — un run VERDE nunca genera un registro (sin falsos positivos).
"""
from src.ci.mapping import to_failure_records
from src.ci.models import CiRunArtifact
from src.ingest.junit import parse_junit
from src.ingest.robot import parse_robot
from src.ingest.testng import parse_testng


# --------------------------------------------------------------------------- JUnit
def test_junit_suite_level_error_is_captured():
    # Fallo de @BeforeClass: Surefire/Gradle lo ponen como <error> hijo de <testsuite>.
    xml = (b'<testsuite name="LoginSuite" tests="0" errors="1" failures="0">'
           b'<error message="BeforeClass boom" type="java.lang.RuntimeException">stack</error>'
           b'</testsuite>')
    recs = parse_junit(xml, project="p")
    assert len(recs) == 1
    assert recs[0].error_type == "java.lang.RuntimeException"


def test_junit_safety_net_declared_failures_but_none_extracted():
    # La cabecera declara failures=1 pero no hay <failure> extraíble → red de seguridad.
    xml = b'<testsuite name="S" tests="1" failures="1"><testcase name="t"/></testsuite>'
    recs = parse_junit(xml, project="p")
    assert len(recs) >= 1


def test_junit_clean_run_no_false_positive():
    xml = (b'<testsuite name="S" tests="2" failures="0" errors="0">'
           b'<testcase name="t1"/><testcase name="t2"/></testsuite>')
    assert parse_junit(xml, project="p") == []


def test_junit_normal_failure_still_works():
    xml = (b'<testsuite name="S" tests="1" failures="1">'
           b'<testcase name="t1" classname="C"><failure message="boom">x</failure></testcase>'
           b'</testsuite>')
    recs = parse_junit(xml, project="p")
    assert len(recs) == 1 and recs[0].test_name == "C.t1"


# --------------------------------------------------------------------------- TestNG
def test_testng_failed_config_method_is_captured():
    xml = (b'<testng-results failed="0" passed="0" skipped="1" total="1"><suite name="S">'
           b'<test name="T"><class name="C">'
           b'<test-method status="FAIL" name="beforeMethod" is-config="true">'
           b'<exception class="java.lang.NullPointerException"><message>NPE in setup</message></exception>'
           b'</test-method>'
           b'<test-method status="SKIP" name="realTest"/>'
           b'</class></test></suite></testng-results>')
    recs = parse_testng(xml, project="p")
    assert len(recs) == 1
    assert recs[0].error_type == "java.lang.NullPointerException"


def test_testng_safety_net_declared_failed_but_none_extracted():
    xml = (b'<testng-results failed="1" total="1"><suite name="S"><test name="T">'
           b'<class name="C"><test-method status="PASS" name="t"/></class>'
           b'</test></suite></testng-results>')
    assert len(parse_testng(xml, project="p")) >= 1


def test_testng_clean_run_no_false_positive():
    xml = (b'<testng-results passed="1" total="1"><suite name="S"><test name="T"><class name="C">'
           b'<test-method status="PASS" name="setup" is-config="true"/>'
           b'<test-method status="PASS" name="realTest"/>'
           b'</class></test></suite></testng-results>')
    assert parse_testng(xml, project="p") == []


# --------------------------------------------------------------------------- Robot
def test_robot_suite_teardown_failure_is_captured():
    # Teardown de suite que falla tras tests en PASS → el suite queda FAIL sin tests fallidos.
    xml = (b'<robot><suite name="MySuite">'
           b'<test name="t1"><status status="PASS"/></test>'
           b'<kw name="Suite Teardown" type="teardown">'
           b'<msg level="FAIL">Teardown failed: connection closed</msg><status status="FAIL"/></kw>'
           b'<status status="FAIL"/></suite></robot>')
    recs = parse_robot(xml, project="p")
    assert len(recs) == 1
    assert "connection closed" in recs[0].message


def test_robot_clean_run_no_false_positive():
    xml = (b'<robot><suite name="S"><test name="t1"><status status="PASS"/></test>'
           b'<status status="PASS"/></suite></robot>')
    assert parse_robot(xml, project="p") == []


# --------------------------------------------------------------------------- Webhook mapping
def _art(tests):
    return CiRunArtifact.model_validate(
        {"project": "demo", "org_id": "o", "commit_sha": "sha", "tests": tests})


def test_mapping_failed_without_message_is_kept():
    # Un fallo sin mensaje NO debe descartarse (antes → 0 records → cert verde de run rojo).
    recs = to_failure_records(_art([{"test_name": "c", "status": "fail"}]))
    assert len(recs) == 1
    assert recs[0].message  # placeholder no vacío


def test_mapping_pass_and_skipped_still_excluded():
    recs = to_failure_records(_art([
        {"test_name": "a", "status": "pass"},
        {"test_name": "b", "status": "skipped"},
    ]))
    assert recs == []
