import json
import pathlib

from src.ci.models import CiRunArtifact

FIX = pathlib.Path("scripts/demo_fixtures")


def _load(name):
    data = json.loads((FIX / name).read_text())
    data["org_id"] = "00000000-0000-0000-0000-000000000000"  # placeholder válido para la validación
    return CiRunArtifact.model_validate(data)


def test_all_fixtures_are_valid_artifacts():
    for name in ("flaky.json", "maintenance_green.json", "maintenance_red.json", "real.json", "fresh_push.json"):
        art = _load(name)
        assert art.tests, f"{name} sin tests"


def test_maintenance_pair_has_doms_and_locator_change():
    green = _load("maintenance_green.json")
    red = _load("maintenance_red.json")
    assert green.tests[0].status == "pass" and green.tests[0].dom and "submit" in green.tests[0].dom
    assert red.tests[0].status == "fail" and red.tests[0].dom and "send" in red.tests[0].dom
    assert green.tests[0].test_name == red.tests[0].test_name   # mismo test → baseline


def test_flaky_and_real_shapes():
    flaky = _load("flaky.json")
    real = _load("real.json")
    assert flaky.tests[0].status == "flaky" or flaky.tests[0].retried   # señal de flaky
    assert real.tests[0].status == "fail" and real.tests[0].error_type  # fallo de aserción
