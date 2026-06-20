import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type, strip_ansi

_FAILED = {"failed", "timedout", "interrupted"}


def _walk(suites, project, records: List[FailureRecord]) -> None:
    for suite in suites or []:
        for spec in suite.get("specs") or []:
            title = spec.get("title") or "unknown"
            for test in spec.get("tests") or []:
                pname = test.get("projectName")
                name = f"{title} ({pname})" if pname else title
                for result in test.get("results") or []:
                    if (result.get("status") or "").lower() not in _FAILED:
                        continue
                    err = result.get("error") or {}
                    message = strip_ansi((err.get("message") or "").strip())
                    trace = strip_ansi((err.get("stack") or "").strip()) or None
                    records.append(
                        FailureRecord(
                            test_name=name,
                            error_type=parse_error_type(message),
                            message=message,
                            trace=trace,
                            project=project,
                            source="playwright",
                        )
                    )
        _walk(suite.get("suites"), project, records)


def parse_playwright(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea el JSON del reporter de Playwright; devuelve los results fallidos."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Playwright JSON: {exc}") from exc
    records: List[FailureRecord] = []
    _walk(obj.get("suites") if isinstance(obj, dict) else None, project, records)
    return records
