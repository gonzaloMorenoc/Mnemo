import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_cucumber(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un cucumber.json; devuelve los steps con result.status 'failed'."""
    try:
        features = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Cucumber JSON: {exc}") from exc
    if not isinstance(features, list):
        raise ValueError("Cucumber JSON must be a list of features")
    records: List[FailureRecord] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        fname = feature.get("name") or "Feature"
        for element in feature.get("elements") or []:
            sname = element.get("name") or "Scenario"
            for step in element.get("steps") or []:
                result = step.get("result") or {}
                if (result.get("status") or "").lower() != "failed":
                    continue
                message = (result.get("error_message") or "").strip()
                records.append(
                    FailureRecord(
                        test_name=f"{fname} / {sname}",
                        error_type=parse_error_type(message),
                        message=message,
                        trace=message or None,
                        project=project,
                        source="cucumber",
                    )
                )
    return records
