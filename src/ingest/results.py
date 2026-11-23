"""Resultados por test (pasados incluidos) de un report, para `test_results`.

Los parsers de `src/ingest/*` solo extraen los fallos (FailureRecord). El triaje
necesita además el resultado de CADA test del run para dos señales:
`retry_passed_in_run` (pasó al reintentar en el mismo run) e `intermittent_same_sha`
(el mismo test pasa y falla con el mismo commit). El webhook los trae ya
estructurados; aquí se sacan del report subido por `/ci/ingest`.

Contrato: el `test_name` es EXACTAMENTE el que pone el parser de fallos del mismo
formato (el triaje cruza ambos por nombre). Formatos sin resultado por test fiable
(robot, testng, cucumber) devuelven lista vacía: el run se ingesta igual, solo que
esas dos señales quedan en falso como hasta ahora. Un report que no parsea también
devuelve lista vacía: la extracción de resultados nunca tumba una ingesta.
"""
import json
from typing import Any, Callable, Dict, List
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

Result = Dict[str, Any]

_PASS, _FAIL, _FLAKY, _SKIPPED = "pass", "fail", "flaky", "skipped"


def _result(test_name: str, status: str, retried: bool = False) -> Result:
    return {"test_name": test_name, "status": status, "retried": retried}


# ---------------------------------------------------------------------------
# JUnit (incluye las extensiones de reintento de Surefire/Gradle)
# ---------------------------------------------------------------------------

def _junit_status(tc) -> Result:
    name = tc.get("name") or "unknown"
    classname = tc.get("classname")
    full = f"{classname}.{name}" if classname else name
    failed = tc.find("failure") is not None or tc.find("error") is not None
    reran = tc.find("rerunFailure") is not None or tc.find("rerunError") is not None
    flaky = tc.find("flakyFailure") is not None or tc.find("flakyError") is not None
    if failed:
        return _result(full, _FAIL, retried=reran)
    if flaky:
        return _result(full, _FLAKY, retried=True)
    if tc.find("skipped") is not None:
        return _result(full, _SKIPPED)
    return _result(full, _PASS)


def _junit_results(data: bytes) -> List[Result]:
    root = ET.fromstring(data)
    return [_junit_status(tc) for tc in root.iter("testcase")]


# ---------------------------------------------------------------------------
# Playwright (JSON reporter)
# ---------------------------------------------------------------------------

_PW_STATUS = {"expected": _PASS, "unexpected": _FAIL, "flaky": _FLAKY, "skipped": _SKIPPED}


def _walk_playwright(suites, acc: List[Result]) -> None:
    for suite in suites or []:
        for spec in suite.get("specs") or []:
            title = spec.get("title") or "unknown"
            for test in spec.get("tests") or []:
                runs = test.get("results") or []
                status = _PW_STATUS.get((test.get("status") or "").lower())
                if not runs or status is None:
                    continue
                pname = test.get("projectName")
                name = f"{title} ({pname})" if pname else title
                acc.append(_result(name, status, retried=len(runs) > 1))
        _walk_playwright(suite.get("suites"), acc)


def _playwright_results(data: bytes) -> List[Result]:
    obj = json.loads(data)
    acc: List[Result] = []
    _walk_playwright(obj.get("suites") if isinstance(obj, dict) else None, acc)
    return acc


# ---------------------------------------------------------------------------
# Cypress (Mochawesome) y Allure
# ---------------------------------------------------------------------------

_CYPRESS_STATUS = {"passed": _PASS, "failed": _FAIL, "pending": _SKIPPED, "skipped": _SKIPPED}
_ALLURE_STATUS = {"passed": _PASS, "failed": _FAIL, "broken": _FAIL, "skipped": _SKIPPED}


def _collect_cypress(suite, acc: List[Result]) -> None:
    for test in suite.get("tests") or []:
        status = _CYPRESS_STATUS.get((test.get("state") or "").lower())
        if status is not None:
            name = test.get("fullTitle") or test.get("title") or "unknown"
            acc.append(_result(name, status))
    for sub in suite.get("suites") or []:
        _collect_cypress(sub, acc)


def _cypress_results(data: bytes) -> List[Result]:
    obj = json.loads(data)
    acc: List[Result] = []
    for result in (obj.get("results") if isinstance(obj, dict) else None) or []:
        _collect_cypress(result, acc)
    return acc


def _allure_results(data: bytes) -> List[Result]:
    obj = json.loads(data)
    items = obj if isinstance(obj, list) else [obj]
    acc: List[Result] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = _ALLURE_STATUS.get((item.get("status") or "").lower())
        if status is not None:
            acc.append(_result(item.get("name") or item.get("fullName") or "unknown", status))
    return acc


_EXTRACTORS: Dict[str, Callable[[bytes], List[Result]]] = {
    "junit": _junit_results,
    "playwright": _playwright_results,
    "cypress": _cypress_results,
    "allure": _allure_results,
}


def extract_results(source: str, data: bytes) -> List[Result]:
    """Resultado por test del report, o [] si el formato no lo soporta o no parsea."""
    extractor = _EXTRACTORS.get(source)
    if extractor is None:
        return []
    try:
        return extractor(data)
    except (ParseError, DefusedXmlException, json.JSONDecodeError, ValueError, KeyError,
            TypeError, AttributeError):
        return []
