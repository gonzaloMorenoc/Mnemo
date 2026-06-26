# Bloque A · PR-2 — Salvaguardas + higiene — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Salvaguarda anti-enmascaramiento en el self-heal (4b), modelo LLM por defecto vigente, y un primer paso de archivado del RAG legacy para que el repo cuente un producto.

**Architecture:** Cambios quirúrgicos en `actions/` (advertencia + flag), `llm/factory.py` (constante), y un movimiento conservador de artefactos legacy (docs/script) + un `legacy/README.md` que documenta la separación; la extracción de un entrypoint limpio del Autopilot queda como follow-up.

**Tech Stack:** Python, pytest.

## Global Constraints

- **4b sin ingesta nueva:** la salvaguarda es advertencia + flag `masking_risk`; la versión robusta (señal `commit_touched_prod` desde el diff) es follow-up (4a).
- **5b conservador:** mover SOLO lo que el Autopilot (`src/api_v2.py`, `src/triage/`, `src/actions/`, `src/certify/`, `src/defects/`) no importe; NO desmantelar `api.py` (aún hostea el Autopilot vía `v2_router`) ni mover módulos RAG `src/` compartidos. Confirmado por grep: `api.py` importa `loader/vector_store/model/evaluator/history/inspector` (legacy) **y** `v2_router` (Autopilot); `structured_analyzer` lo usa `api_v2` → NO se tocan en este PR.
- `python3 -m pytest`. Commits `feat:`/`fix:`/`chore:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: 4b — self-heal anti-enmascaramiento (advertencia + `masking_risk`)

**Files:** Modify `src/actions/selfheal/selfheal.py` (payload), `src/actions/service.py` (`_self_heal_body`); Test: extend `tests/test_selfheal_actuator.py` and `tests/test_actions_service.py` (or wherever `_self_heal_body` is tested).

**Interfaces:** Produces — `SelfHealActuator.propose(...)` payload now includes `"masking_risk": True`; `_self_heal_body(payload)` includes a masking-risk warning.

- [ ] **Step 1: Write the failing tests.** In `tests/test_selfheal_actuator.py`, add an assertion to the existing "produces a proposal" test (or a new test) that the payload carries `masking_risk`:

```python
def test_proposal_payload_flags_masking_risk(self):
    # reuse this file's existing green/failure DOM + context fixture that yields a proposal
    actuator = SelfHealActuator()
    proposal = actuator.propose(verdict, context)   # the context that already yields a heal in this file
    assert proposal is not None
    assert proposal.payload["masking_risk"] is True
```

And in the `_self_heal_body` test (find it: `grep -rn "_self_heal_body" tests/`), assert the warning text appears:

```python
def test_self_heal_body_includes_masking_warning():
    from src.actions.service import _self_heal_body
    body = _self_heal_body({"broken_locator": "a", "suggested_locator": "b", "file": "t.spec.ts", "reasoning": "r"})
    assert "enmascarar una regresión" in body
    assert "cambio de UI legítimo" in body
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_selfheal_actuator.py -q` and the service test.

- [ ] **Step 3: Implement.** In `src/actions/selfheal/selfheal.py`, add `"masking_risk": True` to the `ActionProposal` payload (the dict in `propose`, currently `{"broken_locator": ..., "suggested_locator": ..., "candidates": ..., "reasoning": ..., "file": ...}`):

```python
            return ActionProposal(
                kind="self_heal",
                payload={"broken_locator": broken_str, "suggested_locator": top.locator,
                         "candidates": cands, "reasoning": reasoning,
                         "file": context.get("file"), "masking_risk": True},
                summary=f"Self-heal: {broken_str} → {top.locator}",
            )
```

In `src/actions/service.py`, update `_self_heal_body` to add the warning before the final draft-PR note:

```python
def _self_heal_body(payload: Dict[str, Any]) -> str:
    return (
        "**Self-heal de locator** (Mnemo Autopilot, Nivel 2).\n\n"
        f"- Locator roto: `{payload.get('broken_locator', '')}`\n"
        f"- Locator sugerido: `{payload.get('suggested_locator', '')}`\n"
        f"- Archivo: `{payload.get('file', '')}`\n\n"
        f"## Razonamiento\n{payload.get('reasoning', '')}\n\n"
        "> ⚠️ **Verificar:** si este cambio de UI proviene de un cambio en el código de "
        "producción, curar el locator podría enmascarar una regresión real. Confirmar que es "
        "un cambio de UI legítimo antes de aprobar.\n\n"
        "> PR borrador automático — requiere revisión humana; nunca auto-merge."
    )
```

- [ ] **Step 4: Run, expect PASS** — the two test files, then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/actions/selfheal/selfheal.py src/actions/service.py tests/test_selfheal_actuator.py tests/test_actions_service.py
git commit -m "fix(selfheal): advertencia anti-enmascaramiento en el PR + flag masking_risk

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

> **Verificación (no cambio):** `src/triage/engine.py` R3 ya exige `not signals.assertion_failure` (línea 32: `if (signals.locator_error and not signals.assertion_failure and signals.has_green_baseline and signals.dom_changed)`), por lo que un fallo de aserción real concurrente no se clasifica "maintenance". No tocar engine.py.

---

## Task 2: 5a — modelo LLM por defecto vigente

**Files:** Modify `src/llm/factory.py`; Test `tests/test_llm_factory.py` (extend if exists, else create).

**Interfaces:** Produces — `_DEFAULT_MODELS["anthropic"] == "claude-haiku-4-5-20251001"`.

- [ ] **Step 1: Write the failing test** in `tests/test_llm_factory.py`:

```python
from src.llm.factory import _DEFAULT_MODELS


def test_anthropic_default_is_current_model():
    assert _DEFAULT_MODELS["anthropic"] == "claude-haiku-4-5-20251001"
    assert "3-5" not in _DEFAULT_MODELS["anthropic"]   # ya no el alias obsoleto

def test_ollama_default_unchanged():
    assert _DEFAULT_MODELS["ollama"] == "deepseek-r1:8b"   # el default on-prem no cambia
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_llm_factory.py -q`.

- [ ] **Step 3: Implement** in `src/llm/factory.py`: change the `anthropic` entry of `_DEFAULT_MODELS`:

```python
_DEFAULT_MODELS = {
    "ollama": "deepseek-r1:8b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_llm_factory.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/llm/factory.py tests/test_llm_factory.py
git commit -m "chore(llm): fijar el modelo Anthropic por defecto a uno vigente (Haiku 4.5)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: 5b — archivar el legacy seguro + documentar la separación

**Files:** Move `docs/DEMO.md` → `legacy/DEMO.md`; move `scripts/seed_demo.py` → `legacy/seed_demo.py`; Create `legacy/README.md`.

**Interfaces:** Produces — `legacy/` con los artefactos del flujo anterior + un README que documenta qué es legacy vs Autopilot.

- [ ] **Step 1: Confirm the moves are safe.** Run:
```bash
grep -rn "seed_demo" src/ scripts/ tests/ Dockerfile* docker-compose* 2>/dev/null | grep -v "scripts/seed_demo.py"
grep -rn "DEMO.md" src/ tests/ 2>/dev/null
```
Expected: no production import of `seed_demo` from the Autopilot (a reference in `docs/` or `README` is fine). If `scripts/docker_init.py` or a Dockerfile imports `seed_demo`, STOP and report — it's not safe to move; document it instead.

- [ ] **Step 2: Move the legacy artifacts** (use `git mv` to preserve history):
```bash
mkdir -p legacy
git mv docs/DEMO.md legacy/DEMO.md
git mv scripts/seed_demo.py legacy/seed_demo.py
```

- [ ] **Step 3: Write `legacy/README.md`:**
```markdown
# Legacy — SmartErrorDebugger (producto anterior)

Este directorio conserva artefactos del **producto anterior** de Mnemo: un asistente RAG
de depuración de errores ("SmartErrorDebugger"). El producto actual es **Mnemo Autopilot**
(ingeniero de QA autónomo: triaje → acción Nivel 2 → Release Assurance Certificate + gate),
cuyo código vive en `src/api_v2.py` + `src/triage/`, `src/actions/`, `src/certify/`, `src/defects/`.

## Estado de la convivencia (a 2026-06-26)
- `api.py` (raíz) es el FastAPI **legacy** (monta `BugAnalyzer`/`qa_chain` RAG) y **además**
  monta el router del Autopilot (`v2_router`). Los módulos RAG (`src/loader.py`,
  `src/vector_store.py`, `src/model.py`, `src/evaluator.py`, `src/history.py`,
  `src/inspector.py`, `src/retriever.py`) los usa `api.py`.
- `src/structured_analyzer.py` (análisis RAG estructurado) lo consume `src/api_v2.py` por un
  endpoint heredado; se reutilizará para la causa-raíz multimodal (Bloque B).

## Archivado aquí
- `DEMO.md` — guion de demo del flujo RAG anterior (no del Autopilot).
- `seed_demo.py` — seed del flujo anterior.

## Follow-up (no en este PR)
Extraer un entrypoint limpio del Autopilot (un `app` que monte solo `v2_router`) y mover los
módulos RAG a `legacy/` una vez `api.py` deje de ser el host del Autopilot. Es un esfuerzo
aparte (toca despliegue/Docker), no un cambio de higiene.
```

- [ ] **Step 4: Verify nothing broke.**
```bash
python3 -c "import src.api_v2"   # el Autopilot importa sin el legacy movido
python3 -m pytest -m "not integration" -q   # green
```
If `import src.api_v2` fails or the suite breaks, the move touched something shared — revert that file and document it in `legacy/README.md` instead.

- [ ] **Step 5: Commit**

```bash
git add legacy/ docs/ scripts/
git commit -m "chore(repo): archivar el legacy seguro (DEMO/seed) + documentar la separación legacy/Autopilot

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Alcance real de 5b:** el grep confirmó que `api.py` entrelaza legacy + Autopilot y que `structured_analyzer` lo usa `api_v2`; por eso este PR solo archiva lo seguro (docs/script) y **documenta** la separación. El archivado completo (extraer entrypoint + mover módulos RAG) es un follow-up mayor — señalado en `legacy/README.md`.
- **4a (diferido):** señal `commit_touched_prod` desde el diff del commit → R3 cede si el commit tocó código de producción. Requiere ingerir los archivos cambiados (reporter o GitHub compare API).
- **masking_risk** queda en el payload de la acción (visible en la bandeja del frontend); no se toca el `evidence` del certificado (que deriva de los verdicts, no de las acciones).
- **Fuera de alcance:** Bloque B (IA generativa), C (demo), D (pitch).
