import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type

FAILED_STATUSES = {"failed", "broken"}


def parse_allure(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea uno o varios Allure result objects; devuelve solo failed/broken."""
    obj = json.loads(data)
    items = obj if isinstance(obj, list) else [obj]
    records: List[FailureRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = (item.get("status") or "").lower()
        if status not in FAILED_STATUSES:
            continue
        details = item.get("statusDetails") or {}
        message = (details.get("message") or "").strip()
        trace = details.get("trace") or None
        records.append(
            FailureRecord(
                test_name=item.get("name") or item.get("fullName") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="allure",
            )
        )
    return records
