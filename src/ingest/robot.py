import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_robot(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un output.xml de Robot Framework; devuelve los tests con status FAIL."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid Robot XML: {exc}") from exc
    records: List[FailureRecord] = []
    for test in root.iter("test"):
        status = test.find("status")
        if status is None or (status.get("status") or "").upper() != "FAIL":
            continue
        message = (status.text or "").strip()
        fail_msgs = [
            m.text.strip()
            for m in test.iter("msg")
            if (m.get("level") or "").upper() == "FAIL" and m.text
        ]
        if not message and fail_msgs:
            message = fail_msgs[-1]
        trace = "\n".join(fail_msgs) or None
        records.append(
            FailureRecord(
                test_name=test.get("name") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="robot",
            )
        )
    return records
