from src.ingest.models import FailureRecord
from src.jira.models import JiraBug


def bug_to_record(bug: JiraBug, *, project: str) -> FailureRecord:
    """Mapea un JiraBug a un FailureRecord sintético (source='jira')."""
    return FailureRecord(
        test_name=bug.key or "unknown",
        error_type=bug.issue_type or None,
        message=bug.summary,
        trace=bug.description or None,
        project=project,
        source="jira",
    )
