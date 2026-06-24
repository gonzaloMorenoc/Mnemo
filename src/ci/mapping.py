from typing import List

from src.ci.models import CiRunArtifact
from src.ingest.models import FailureRecord, parse_error_type

_FAILED = {"fail", "flaky"}


def to_failure_records(artifact: CiRunArtifact) -> List[FailureRecord]:
    """Convierte los tests fallidos/flaky con mensaje en FailureRecord[].

    Los pass/skipped y los fallos sin mensaje se excluyen (no alimentan el DNA).
    """
    records: List[FailureRecord] = []
    for t in artifact.tests:
        if t.status not in _FAILED or not t.message:
            continue
        records.append(
            FailureRecord(
                test_name=t.test_name,
                error_type=t.error_type or parse_error_type(t.message),
                message=t.message,
                trace=t.trace,
                project=artifact.project,
                source=artifact.source,
                file=t.file,
                line=t.line,
            )
        )
    return records
