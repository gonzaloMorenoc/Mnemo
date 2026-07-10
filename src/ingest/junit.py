import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import (
    FailureRecord,
    int_attr,
    parse_error_type,
    synthetic_failure_record,
)


def parse_junit(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea JUnit XML; devuelve testcases con <failure>/<error>, fallos a nivel de
    suite (@BeforeClass) y una red de seguridad si la cabecera declara fallos sin extraer."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid JUnit XML: {exc}") from exc
    records: List[FailureRecord] = []
    for tc in root.iter("testcase"):
        node = tc.find("failure")
        if node is None:
            node = tc.find("error")
        if node is None:
            continue
        name = tc.get("name") or "unknown"
        classname = tc.get("classname")
        full = f"{classname}.{name}" if classname else name
        message = (node.get("message") or "").strip()
        error_type = node.get("type") or parse_error_type(message)
        trace = (node.text or "").strip() or None
        records.append(
            FailureRecord(
                test_name=full,
                error_type=error_type,
                message=message,
                trace=trace,
                project=project,
                source="junit",
            )
        )

    # Fallos a nivel de suite (setup de clase / @BeforeClass): Surefire/Gradle los ponen
    # como <error>/<failure> hijo DIRECTO de <testsuite>, no dentro de un <testcase>.
    for suite in root.iter("testsuite"):
        node = suite.find("error")
        if node is None:
            node = suite.find("failure")
        if node is None:
            continue
        suite_name = suite.get("name") or "suite"
        message = (node.get("message") or "").strip()
        error_type = node.get("type") or parse_error_type(message)
        trace = (node.text or "").strip() or None
        records.append(
            FailureRecord(
                test_name=f"{suite_name} (suite setup)",
                error_type=error_type,
                message=message or "Suite-level error (sin mensaje)",
                trace=trace,
                project=project,
                source="junit",
            )
        )

    # Red de seguridad: la cabecera declara fallos pero no se extrajo ninguno.
    if not records:
        declared = max(
            (int_attr(n, "failures") + int_attr(n, "errors")
             for n in [root, *root.iter("testsuite")]),
            default=0,
        )
        if declared > 0:
            records.append(synthetic_failure_record(project=project, source="junit", declared=declared))
    return records
