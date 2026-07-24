"""Resumen de ejecución (manifiesto) por formato de reporte: total/passed/failed/
skipped/flaky. Independiente de la extracción de fallos (los parsers de src/ingest/*
siguen sacando solo los FailureRecord). `complete = total > 0`: el acta atesta el
artefacto tal como se subió; la completitud real del run la cierra la aprobación humana.
"""
import json
from dataclasses import dataclass
from typing import Optional
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

from src.ingest.models import int_attr, strip_ansi_bytes


@dataclass
class RunSummary:
    total: int
    passed: int
    failed: int
    skipped: int
    flaky: int = 0
    complete: bool = False
    source_format: str = ""


def _summarize_junit(data: bytes) -> RunSummary:
    root = ET.fromstring(data)
    # Preferir el agregado de la raíz (un <testsuite> único o <testsuites tests=…>);
    # si la raíz <testsuites> NO trae agregado, SUMAR los <testsuite> hijos (no max,
    # que subcontaría un run multi-suite).
    if root.get("tests") is not None:
        total = int_attr(root, "tests")
        failed = int_attr(root, "failures") + int_attr(root, "errors")
        skipped = int_attr(root, "skipped")
    else:
        suites = list(root.iter("testsuite"))
        total = sum(int_attr(s, "tests") for s in suites)
        failed = sum(int_attr(s, "failures") + int_attr(s, "errors") for s in suites)
        skipped = sum(int_attr(s, "skipped") for s in suites)
    passed = max(total - failed - skipped, 0)
    return RunSummary(total, passed, failed, skipped, complete=total > 0, source_format="junit")


def _summarize_testng(data: bytes) -> RunSummary:
    root = ET.fromstring(strip_ansi_bytes(data))
    total = int_attr(root, "total")
    failed = int_attr(root, "failed")
    # `skipped` cuadra con el `total` de la cabecera (que excluye 'ignored').
    skipped = int_attr(root, "skipped")
    passed = int_attr(root, "passed")
    return RunSummary(total, passed, failed, skipped, complete=total > 0, source_format="testng")


def _summarize_robot(data: bytes) -> RunSummary:
    root = ET.fromstring(strip_ansi_bytes(data))
    # El <stat> "All Tests" (o el de mayor suma) tiene los totales del run.
    best = None
    for stat in root.iter("stat"):
        p, f, s = int_attr(stat, "pass"), int_attr(stat, "fail"), int_attr(stat, "skip")
        if best is None or (p + f + s) > (best[0] + best[1] + best[2]):
            best = (p, f, s)
    p, f, s = best or (0, 0, 0)
    total = p + f + s
    return RunSummary(total, p, f, s, complete=total > 0, source_format="robot")


def _summarize_cypress(data: bytes) -> RunSummary:
    obj = json.loads(data)
    stats = (obj.get("stats") if isinstance(obj, dict) else None) or {}
    total = int(stats.get("tests") or 0)
    passed = int(stats.get("passes") or 0)
    failed = int(stats.get("failures") or 0)
    skipped = int(stats.get("pending") or 0) + int(stats.get("skipped") or 0)
    return RunSummary(total, passed, failed, skipped, complete=total > 0, source_format="cypress")


def _summarize_playwright(data: bytes) -> RunSummary:
    obj = json.loads(data)
    stats = (obj.get("stats") if isinstance(obj, dict) else None) or {}
    passed = int(stats.get("expected") or 0)
    failed = int(stats.get("unexpected") or 0)
    flaky = int(stats.get("flaky") or 0)
    skipped = int(stats.get("skipped") or 0)
    total = passed + failed + flaky + skipped
    return RunSummary(total, passed, failed, skipped, flaky=flaky, complete=total > 0,
                      source_format="playwright")


def _summarize_allure(data: bytes) -> RunSummary:
    obj = json.loads(data)
    items = obj if isinstance(obj, list) else [obj]
    items = [i for i in items if isinstance(i, dict)]

    def n(*statuses):
        return sum(1 for i in items if (i.get("status") or "").lower() in statuses)

    total = len(items)
    return RunSummary(total, n("passed"), n("failed", "broken"), n("skipped"),
                      complete=total > 0, source_format="allure")


def _summarize_cucumber(data: bytes) -> RunSummary:
    features = json.loads(data)
    if not isinstance(features, list):
        raise ValueError("Cucumber JSON must be a list of features")
    passed = failed = skipped = 0
    for feature in features:
        if not isinstance(feature, dict):
            continue
        for element in feature.get("elements") or []:
            # Los 'background' llevan steps pero NO son escenarios → no cuentan.
            if (element.get("type") or "scenario").lower() != "scenario":
                continue
            statuses = [(st.get("result") or {}).get("status", "").lower()
                        for st in element.get("steps") or []]
            if any(s == "failed" for s in statuses):
                failed += 1
            elif statuses and all(s == "passed" for s in statuses):
                passed += 1
            else:
                skipped += 1
    total = passed + failed + skipped
    return RunSummary(total, passed, failed, skipped, complete=total > 0, source_format="cucumber")


_SUMMARIZERS = {
    "junit": _summarize_junit, "testng": _summarize_testng, "robot": _summarize_robot,
    "cypress": _summarize_cypress, "playwright": _summarize_playwright,
    "allure": _summarize_allure, "cucumber": _summarize_cucumber,
}


def summarize(source: str, data: bytes) -> Optional[RunSummary]:
    """RunSummary del reporte, o None si el formato no se soporta o el parseo falla
    (→ el manifiesto queda ausente → el veredicto será sin_confirmar)."""
    fn = _SUMMARIZERS.get(source)
    if fn is None:
        return None
    try:
        return fn(data)
    except (ParseError, DefusedXmlException, json.JSONDecodeError, ValueError, KeyError,
            TypeError, AttributeError):
        return None


def to_manifest(summary: RunSummary, *, artifact_sha256: str,
                commit_sha: Optional[str]) -> dict:
    return {"total": summary.total, "passed": summary.passed, "failed": summary.failed,
            "skipped": summary.skipped, "flaky": summary.flaky, "complete": summary.complete,
            "source_format": summary.source_format, "artifact_sha256": artifact_sha256,
            "commit_sha": commit_sha}
