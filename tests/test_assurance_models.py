from src.multitenant_models import (
    IngestReportResponse, DefectFamilyResponse, FailureRef,
    DefectFamilySummary, DefectLineageResponse,
)


def test_ingest_report_response():
    r = IngestReportResponse(run_id="r1", ingested=3, known=1, novel=2)
    assert r.run_id == "r1" and r.novel == 2


def test_defect_family_response_defaults():
    f = DefectFamilyResponse(id="f1", title="Timeout", status="open", occurrence_count=2)
    assert f.projects == [] and f.first_seen is None


def test_defect_lineage_response():
    lin = DefectLineageResponse(
        family=DefectFamilySummary(id="f1", title="T", status="open", occurrence_count=1),
        failures=[FailureRef(id="x", test_name="t", project="p", source="allure")],
    )
    assert lin.family.id == "f1" and lin.failures[0].source == "allure"


def test_defect_lineage_response_empty():
    lin = DefectLineageResponse()
    assert lin.family is None and lin.failures == []
