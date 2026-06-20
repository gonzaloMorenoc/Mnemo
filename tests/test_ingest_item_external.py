from src.defects.repository import IngestItem
from src.ingest.models import FailureRecord


def _rec():
    return FailureRecord(test_name="t", error_type="Bug", message="m", trace=None,
                         project="p", source="jira")


def test_ingest_item_external_fields_default_none():
    item = IngestItem(rec=_rec(), fingerprint="fp", embedding=[0.0] * 384)
    assert item.external_ref is None
    assert item.external_url is None


def test_ingest_item_accepts_external_fields():
    item = IngestItem(rec=_rec(), fingerprint="fp", embedding=[0.0] * 384,
                      external_ref="PROJ-1", external_url="https://x/browse/PROJ-1")
    assert item.external_ref == "PROJ-1"
    assert item.external_url == "https://x/browse/PROJ-1"
