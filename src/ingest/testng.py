import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import FailureRecord, parse_error_type, strip_ansi, strip_ansi_bytes


def parse_testng(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un testng-results.xml; devuelve los test-method con status FAIL."""
    data = strip_ansi_bytes(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid TestNG XML: {exc}") from exc
    records: List[FailureRecord] = []
    for cls in root.iter("class"):
        classname = cls.get("name") or ""
        for tm in cls.findall("test-method"):
            if (tm.get("status") or "").upper() != "FAIL":
                continue
            name = tm.get("name") or "unknown"
            full = f"{classname}.{name}" if classname else name
            exc_node = tm.find("exception")
            error_type = exc_node.get("class") if exc_node is not None else None
            message = ""
            trace = None
            if exc_node is not None:
                msg_node = exc_node.find("message")
                if msg_node is not None and msg_node.text:
                    message = strip_ansi(msg_node.text.strip())
                st_node = exc_node.find("full-stacktrace")
                if st_node is not None and st_node.text:
                    trace = strip_ansi(st_node.text.strip()) or None
            if not error_type:
                error_type = parse_error_type(message)
            records.append(
                FailureRecord(
                    test_name=full,
                    error_type=error_type,
                    message=message,
                    trace=trace,
                    project=project,
                    source="testng",
                )
            )
    return records
