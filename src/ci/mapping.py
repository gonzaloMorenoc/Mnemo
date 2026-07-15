from typing import List

from src.ci.models import CiRunArtifact
from src.ingest.models import FailureRecord, parse_error_type

_FAILED = {"fail", "flaky"}


def to_failure_records(artifact: CiRunArtifact) -> List[FailureRecord]:
    """Convierte los tests fallidos/flaky en FailureRecord[].

    Los pass/skipped se excluyen. Un fallo SIN mensaje NO se descarta (antes se
    perdía → 0 registros → acta 'apto' de un run rojo): se sintetiza un placeholder.
    """
    records: List[FailureRecord] = []
    for t in artifact.tests:
        if t.status not in _FAILED:
            continue
        message = t.message or f"{t.status} sin mensaje reportado"
        records.append(
            FailureRecord(
                test_name=t.test_name,
                error_type=t.error_type or parse_error_type(message),
                message=message,
                trace=t.trace,
                project=artifact.project,
                source=artifact.source,
                file=t.file,
                line=t.line,
            )
        )
    return records
