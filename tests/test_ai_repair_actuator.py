from src.actions.ai_repair import AIRepairActuator


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _Boom:
    def complete(self, prompt): raise RuntimeError("down")


_SOURCE = "test('checkout', async ({page}) => {\n  await expect(page).toHaveTitle('Old');\n});"
_CTX = {"file": "tests/checkout.spec.ts", "test_source": _SOURCE, "error_message": "expected 'New' got 'Old'"}
_VERDICT = {"category": "maintenance"}


def test_proposes_patch_when_old_block_present():
    out = '{"old_block":"await expect(page).toHaveTitle(\'Old\');","new_block":"await expect(page).toHaveTitle(\'New\');","explanation":"título actualizado","confidence":0.8,"citations":["test_source"]}'
    p = AIRepairActuator(_Provider(out)).propose(_VERDICT, _CTX)
    assert p is not None and p.kind == "self_heal"
    assert p.payload["ai_repair"] is True and p.payload["masking_risk"] is True
    assert p.payload["broken_locator"] == "await expect(page).toHaveTitle('Old');"
    assert p.payload["suggested_locator"] == "await expect(page).toHaveTitle('New');"
    assert p.payload["file"] == "tests/checkout.spec.ts"


def test_degrades_when_old_block_not_in_source():
    out = '{"old_block":"NO ESTÁ EN EL CÓDIGO","new_block":"x","confidence":0.9,"citations":[]}'
    assert AIRepairActuator(_Provider(out)).propose(_VERDICT, _CTX) is None


def test_degrades_when_old_equals_new():
    blk = "await expect(page).toHaveTitle('Old');"
    out = '{"old_block":"%s","new_block":"%s","confidence":0.9}' % (blk, blk)
    assert AIRepairActuator(_Provider(out)).propose(_VERDICT, _CTX) is None


def test_degrades_without_test_source():
    assert AIRepairActuator(_Provider("{}")).propose(_VERDICT, {"file": "x.ts", "error_message": "e"}) is None


def test_degrades_without_llm():
    assert AIRepairActuator(_Boom()).propose(_VERDICT, _CTX) is None


def test_degrades_when_confidence_low():
    blk = "await expect(page).toHaveTitle('Old');"
    new = "await expect(page).toHaveTitle('New');"
    out = '{"old_block":"%s","new_block":"%s","explanation":"x","confidence":0.2,"citations":[]}' % (blk, new)
    assert AIRepairActuator(_Provider(out)).propose(_VERDICT, _CTX) is None


def test_source_is_truncated_before_llm():
    captured = {}
    class _Spy:
        def complete(self, prompt):
            captured["prompt"] = prompt
            return '{"old_block":"x","new_block":"y","confidence":0.9}'
    big = "A" * 20000
    ctx = {"file": "t.spec.ts", "test_source": big, "error_message": "e"}
    AIRepairActuator(_Spy()).propose({"category": "maintenance"}, ctx)
    # el prompt no debe contener el source completo (truncado a _MAX_SOURCE=8000;
    # el template _PROMPT aporta ~3 'A' propias, por eso se tolera hasta 8010)
    assert captured["prompt"].count("A") <= 8010
