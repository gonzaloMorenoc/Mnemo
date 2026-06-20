import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type, strip_ansi


def _collect(suite, acc: list) -> None:
    for test in suite.get("tests") or []:
        acc.append(test)
    for sub in suite.get("suites") or []:
        _collect(sub, acc)


def parse_cypress(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un JSON Mochawesome (Cypress); devuelve los tests fallidos."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Mochawesome JSON: {exc}") from exc
    tests: list = []
    for result in (obj.get("results") if isinstance(obj, dict) else None) or []:
        _collect(result, tests)
    records: List[FailureRecord] = []
    for test in tests:
        state = (test.get("state") or "").lower()
        err = test.get("err") or {}
        if state != "failed" and not err:
            continue
        message = strip_ansi((err.get("message") or "").strip())
        trace = strip_ansi((err.get("estack") or "").strip()) or None
        records.append(
            FailureRecord(
                test_name=test.get("fullTitle") or test.get("title") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="cypress",
            )
        )
    return records
