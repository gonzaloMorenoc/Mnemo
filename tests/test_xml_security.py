"""B9 — los parsers XML deben rechazar entidades/DTD (XXE, billion-laughs).

Con `xml.etree` crudo, una entidad interna se EXPANDE sin error (`&x;`→"boom"),
y un billion-laughs puede agotar la memoria del proceso único (tumba a todos los
tenants). Con `defusedxml` cualquier DTD/entidad se rechaza → ValueError / None.
"""
import pytest

from src.ingest.detect import detect_source
from src.ingest.junit import parse_junit
from src.ingest.robot import parse_robot
from src.ingest.testng import parse_testng

# Entidad interna: prueba determinista de que el procesamiento de entidades está
# desactivado. Con ET crudo esto parsea y expande &x;→"boom" (sin error).
_JUNIT_ENTITY = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "boom">]>'
                 b'<testsuite name="&x;"><testcase name="t"><failure>&x;</failure></testcase></testsuite>')
_TESTNG_ENTITY = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "boom">]>'
                  b'<testng-results failed="1"><suite name="&x;"><test name="T"><class name="C">'
                  b'<test-method status="FAIL" name="m"/></class></test></suite></testng-results>')
_ROBOT_ENTITY = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "boom">]>'
                 b'<robot><suite name="&x;"><test name="t"><status status="FAIL"/></test></suite></robot>')


def test_junit_rejects_xml_entities():
    with pytest.raises(ValueError):
        parse_junit(_JUNIT_ENTITY, project="p")


def test_testng_rejects_xml_entities():
    with pytest.raises(ValueError):
        parse_testng(_TESTNG_ENTITY, project="p")


def test_robot_rejects_xml_entities():
    with pytest.raises(ValueError):
        parse_robot(_ROBOT_ENTITY, project="p")


def test_detect_source_safe_on_entities():
    # detect no debe crashear ni expandir; devuelve None ante XML con DTD/entidad.
    assert detect_source(_JUNIT_ENTITY) is None


def test_normal_xml_still_parses():
    # Control: XML legítimo (sin DTD) sigue funcionando.
    ok = b'<testsuite name="S"><testcase name="t" classname="C"><failure message="boom">x</failure></testcase></testsuite>'
    recs = parse_junit(ok, project="p")
    assert len(recs) == 1 and recs[0].test_name == "C.t"
    assert detect_source(ok) == "junit"
