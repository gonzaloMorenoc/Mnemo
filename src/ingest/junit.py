import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_junit(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea JUnit XML; devuelve testcases con <failure> o <error>."""
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
    return records
