# Bloque A · PR-1 — El certificado honesto — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rellenar el `self_eval` del certificado con métricas deterministas firmadas, reencuadrarlo como "acta de evidencia", y que la confianza baja module el veredicto (cert↔gate consistentes).

**Architecture:** Funciones puras nuevas en `certify/certificate.py` (`compute_confidence`, `compute_self_eval`, y `compute_verdict` con `confidence`); `build_certificate` recibe el `self_eval` ya computado; `CertificateService` y `GateService` lo computan desde `get_calibration_metrics` (ya existe); `render_html` refleja el reencuadre.

**Tech Stack:** Python, pytest. Determinista (sin LLM en el camino del certificado).

## Global Constraints

- El certificado es **puro** y **determinista**; el timestamp/datos se inyectan. La firma Ed25519 cubre el cert completo (incl. `self_eval`).
- **Cert y gate comparten la política §7.1** (`compute_verdict`): no deben divergir. Ambos pasan el mismo `confidence`.
- Umbrales (constantes en `certificate.py`): `confidence="low"` si `n_corrections < 30` **o** `tenant_accuracy < 0.60`; `"high"` si `n_corrections >= 100` **y** `tenant_accuracy >= 0.80`; `"medium"` en otro caso.
- `DATABASE_URL` (.env) = **producción** (tests de integración con cleanup en fixtures). `python3 -m pytest`. Commits `feat:`/`fix:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Funciones puras — `compute_confidence`, `compute_self_eval`, `compute_verdict(confidence)`

**Files:** Modify `src/certify/certificate.py`; Test `tests/test_certificate.py` (extend if exists, else create).

**Interfaces:** Produces — `compute_confidence(calibration: Dict) -> str`; `compute_self_eval(*, calibration: Dict, verdicts: List[Dict], created_at: str) -> Dict`; `compute_verdict(verdicts: List[Dict], confidence: str = "high") -> str`. `calibration` tiene las claves `tenant_accuracy: float`, `n_corrections: int`, `por_categoria_humana: Dict`.

- [ ] **Step 1: Write the failing tests** in `tests/test_certificate.py`:

```python
from src.certify.certificate import compute_confidence, compute_self_eval, compute_verdict


def test_confidence_low_on_cold_start():
    assert compute_confidence({"tenant_accuracy": 0.99, "n_corrections": 5}) == "low"   # n<30
    assert compute_confidence({"tenant_accuracy": 0.50, "n_corrections": 500}) == "low"  # acc<0.60

def test_confidence_high_and_medium():
    assert compute_confidence({"tenant_accuracy": 0.85, "n_corrections": 120}) == "high"
    assert compute_confidence({"tenant_accuracy": 0.85, "n_corrections": 50}) == "medium"  # n entre 30 y 100

def test_self_eval_shape_and_run_composition():
    verdicts = [{"llm_assisted": True}, {"llm_assisted": False}, {"llm_assisted": False}]
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200, "por_categoria_humana": {"real": 10}}
    se = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    assert se["method"] == "deterministic_v1"
    assert se["engine_calibration"] == {"tenant_accuracy": 0.9, "n_corrections": 200, "por_categoria_humana": {"real": 10}}
    assert se["run_composition"] == {"total": 3, "deterministic": 2, "llm_assisted": 1}
    assert se["confidence"] == "high" and se["evaluated_at"] == "2026-06-26T00:00:00Z"

def test_verdict_low_confidence_downgrades_apto_only():
    apto = [{"category": "flaky", "requires_approval": False}]
    assert compute_verdict(apto, confidence="high") == "apto"
    assert compute_verdict(apto, confidence="low") == "apto-con-reservas"
    # no-apto y apto-con-reservas no cambian con confidence
    pend = [{"category": "real", "requires_approval": True}]
    assert compute_verdict(pend, confidence="low") == "no-apto"
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_certificate.py -q` (funciones nuevas / firma de `compute_verdict` sin `confidence`).

- [ ] **Step 3: Implement** in `src/certify/certificate.py`. Add the constants and functions, and extend `compute_verdict`:

```python
_COLD_START_MIN_CORRECTIONS = 30
_LOW_ACCURACY = 0.60
_HIGH_MIN_CORRECTIONS = 100
_HIGH_MIN_ACCURACY = 0.80


def compute_confidence(calibration: Dict[str, Any]) -> str:
    """Confianza del motor en este tenant a partir de su calibración acumulada."""
    n = calibration.get("n_corrections", 0)
    acc = calibration.get("tenant_accuracy", 0.0)
    if n < _COLD_START_MIN_CORRECTIONS or acc < _LOW_ACCURACY:
        return "low"
    if n >= _HIGH_MIN_CORRECTIONS and acc >= _HIGH_MIN_ACCURACY:
        return "high"
    return "medium"


def compute_self_eval(*, calibration: Dict[str, Any], verdicts: List[Dict[str, Any]],
                      created_at: str) -> Dict[str, Any]:
    """Auto-evaluación determinista del motor (deterministic_v1). Pura."""
    total = len(verdicts)
    llm_assisted = sum(1 for v in verdicts if v.get("llm_assisted"))
    return {
        "method": "deterministic_v1",
        "engine_calibration": {
            "tenant_accuracy": calibration.get("tenant_accuracy", 0.0),
            "n_corrections": calibration.get("n_corrections", 0),
            "por_categoria_humana": calibration.get("por_categoria_humana", {}),
        },
        "run_composition": {"total": total, "deterministic": total - llm_assisted,
                            "llm_assisted": llm_assisted},
        "confidence": compute_confidence(calibration),
        "evaluated_at": created_at,
    }
```

And change `compute_verdict`'s signature + the final branch:

```python
def compute_verdict(verdicts: List[Dict[str, Any]], confidence: str = "high") -> str:
    reales_novel_sin_approval = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") == "R5_real_novel" and not v.get("requires_approval"))
    pendientes_approval = sum(1 for v in verdicts if v.get("requires_approval"))
    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        return "no-apto"
    if any(v.get("category") in ("real", "maintenance") for v in verdicts):
        return "apto-con-reservas"
    if confidence == "low":
        return "apto-con-reservas"   # baja calibración del motor → no certificar apto rotundo
    return "apto"
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_certificate.py -q`.

- [ ] **Step 5: Commit**

```bash
git add src/certify/certificate.py tests/test_certificate.py
git commit -m "feat(cert): self_eval determinista + confianza del motor que modula el veredicto

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `build_certificate` — `self_eval` + reencuadre (schema v2, attestation, disclaimer)

**Files:** Modify `src/certify/certificate.py` (`build_certificate`); Test `tests/test_certificate.py`.

**Interfaces:** Consumes — `compute_self_eval` (Task 1). Produces — `build_certificate(*, run, verdicts, sign_offs, mnemo_version, model_version, created_at, self_eval: Dict) -> Dict` con `schema="mnemo.cert.v2"`, `attestation_type`, `disclaimer`, y `self_eval` incrustado; el `verdict` usa `self_eval["confidence"]`.

- [ ] **Step 1: Write the failing test** in `tests/test_certificate.py`:

```python
from src.certify.certificate import build_certificate, compute_self_eval
from src.certify.signing import canonical_json, sign, verify
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def _keys():
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    pub = sk.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def test_build_certificate_is_v2_with_self_eval_and_disclaimer():
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se)
    assert cert["schema"] == "mnemo.cert.v2"
    assert cert["attestation_type"] == "evidence_and_assessment"
    assert "garantía" in cert["disclaimer"].lower()
    assert cert["self_eval"]["confidence"] == "high"
    assert cert["verdict"] == "apto"   # confidence high, todo flaky

def test_low_confidence_self_eval_downgrades_cert_verdict():
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.0, "n_corrections": 0},  # cold-start → low
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se)
    assert cert["verdict"] == "apto-con-reservas"

def test_signature_covers_self_eval():
    priv, pub = _keys()
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se)
    sig = sign(canonical_json(cert), priv)
    assert verify(canonical_json(cert), sig, pub) is True
    cert["self_eval"]["confidence"] = "low"   # tamper
    assert verify(canonical_json(cert), sig, pub) is False
```

- [ ] **Step 2: Run, expect FAIL** (`build_certificate` no acepta `self_eval`, schema es v1).

- [ ] **Step 3: Implement** in `src/certify/certificate.py`. Add the disclaimer constant and update `build_certificate`'s signature, `verdict` line, and returned dict:

```python
_DISCLAIMER = (
    "Este certificado es un acta de evidencia reproducible: registra los fallos observados, "
    "la evaluación del motor de triaje (determinista, auditable) y las aprobaciones humanas. "
    "La 'evaluación' es una señal asistida, no una garantía de ausencia de defectos ni una "
    "certificación de aptitud legal."
)
```

In `build_certificate`: add `self_eval: Dict[str, Any]` to the keyword args; change `verdict = compute_verdict(verdicts)` → `verdict = compute_verdict(verdicts, confidence=self_eval["confidence"])`; and the returned dict:

```python
    return {
        "schema": "mnemo.cert.v2",
        "attestation_type": "evidence_and_assessment",
        "disclaimer": _DISCLAIMER,
        "identity": {"org_id": run["org_id"], "project": run["project"],
                     "commit_sha": run.get("commit_sha"), "run_id": run["run_id"],
                     "created_at": created_at, "mnemo_version": mnemo_version,
                     "model_version": model_version},
        "verdict": verdict,
        "risk_score": risk_score,
        "breakdown": breakdown,
        "evidence": evidence,
        "sign_offs": sign_offs,
        "self_eval": self_eval,
    }
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_certificate.py -q`.

- [ ] **Step 5: Commit**

```bash
git add src/certify/certificate.py tests/test_certificate.py
git commit -m "feat(cert): reencuadre a acta de evidencia (schema v2 + attestation + disclaimer) + self_eval firmado

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Integración — `CertificateService` computa `self_eval`; `GateService` alinea el `confidence`

**Files:** Modify `src/certify/service.py` (`generate`), `src/certify/gate.py` (`publish`); Test `tests/test_certify_service_selfeval.py` (integración).

**Interfaces:** Consumes — `compute_self_eval`, `compute_confidence` (Task 1); `AssuranceRepository.get_calibration_metrics` (`{total, aciertos, accuracy, familias_calibradas, por_categoria}`). Produces — cert con `self_eval` real; gate con el mismo `confidence` que el cert.

- [ ] **Step 1: `CertificateService.generate`** — after fetching `verdicts`, compute the calibration mapping + self_eval and pass it. In `src/certify/service.py`, change the import and the `generate` body:

```python
from src.certify.certificate import build_certificate, compute_self_eval
```

Between `verdicts = self.repo.get_triage_for_run(...)` (with its `if not verdicts` guard) and `cert = build_certificate(...)`:

```python
        raw_cal = self.repo.get_calibration_metrics(user_id=user_id, org_id=meta["org_id"]) or {}
        calibration = {
            "tenant_accuracy": raw_cal.get("accuracy", 0.0),
            "n_corrections": raw_cal.get("total", 0),
            "por_categoria_humana": raw_cal.get("por_categoria", {}),
        }
        self_eval = compute_self_eval(calibration=calibration, verdicts=verdicts, created_at=created_at)
        cert = build_certificate(
            run={"org_id": meta["org_id"], "project": meta["project"],
                 "commit_sha": meta["commit_sha"], "run_id": run_id},
            verdicts=verdicts, sign_offs=[], mnemo_version=self._mnemo_version,
            model_version=self._model_version, created_at=created_at, self_eval=self_eval,
        )
```

- [ ] **Step 2: `GateService.publish`** — compute the same `confidence` and pass it to `compute_verdict`. In `src/certify/gate.py`, change the import and the `verdict =` line:

```python
from src.certify.certificate import compute_confidence, compute_verdict
```

Replace `verdict = compute_verdict(verdicts)` with:

```python
        raw_cal = self.repo.get_calibration_metrics(user_id=user_id, org_id=meta["org_id"]) or {}
        confidence = compute_confidence({"tenant_accuracy": raw_cal.get("accuracy", 0.0),
                                         "n_corrections": raw_cal.get("total", 0)})
        verdict = compute_verdict(verdicts, confidence=confidence)
```

- [ ] **Step 3: Write the integration test** — `tests/test_certify_service_selfeval.py`. Seed an org + a run with one resolved triage verdict; a NEW tenant (no `triage_corrections`) must yield `confidence: "low"` and a cert verdict of `apto-con-reservas` (even when the run itself is clean). Mirror the seeding of `tests/test_certify_repository.py` (read it for the exact fixture pattern — org/user/run/failure/triage_verdict inserts + teardown). Skeleton:

```python
import os, uuid
import psycopg, pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()
DBURL = os.getenv("DATABASE_URL", "")

from src.defects.repository import AssuranceRepository
from src.certify.certificate import compute_self_eval


def test_new_tenant_gets_low_confidence(seeded_clean_run):  # fixture: org/user/run with a clean (flaky) verdict, no corrections
    ctx = seeded_clean_run
    repo = AssuranceRepository(DBURL)
    raw = repo.get_calibration_metrics(user_id=ctx["user_id"], org_id=ctx["org_id"]) or {}
    cal = {"tenant_accuracy": raw.get("accuracy", 0.0), "n_corrections": raw.get("total", 0),
           "por_categoria_humana": raw.get("por_categoria", {})}
    verdicts = repo.get_triage_for_run(user_id=ctx["user_id"], run_id=ctx["run_id"])
    se = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    assert se["confidence"] == "low"           # tenant nuevo, sin correcciones
    assert se["engine_calibration"]["n_corrections"] == 0
```

(Write the `seeded_clean_run` fixture following `test_certify_repository.py`; it must insert at least one `triage_verdicts` row with `status='resolved'` so `get_triage_for_run` returns it. Add teardown that deletes the org + auth user.)

- [ ] **Step 4: Run** — `python3 -m pytest tests/test_certify_service_selfeval.py -q` → PASS. Then `python3 -m pytest -m "not integration" -q` → green (existing cert/gate tests still pass; if any asserted `schema == "mnemo.cert.v1"` or called `build_certificate` without `self_eval`, update them minimally — the cert now requires `self_eval`).

- [ ] **Step 5: Commit**

```bash
git add src/certify/service.py src/certify/gate.py tests/test_certify_service_selfeval.py
git commit -m "feat(cert): el servicio computa self_eval real; el gate alinea el confidence (cert↔gate no divergen)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 4: `render_html` — disclaimer, "evaluación del motor", `self_eval`, terminología honesta

**Files:** Modify `src/certify/render.py`; Test `tests/test_certificate_render.py` (extend if exists).

**Interfaces:** Consumes — el cert con `disclaimer`, `self_eval`, y `evidence[].rule_applied`. Produces — HTML con el disclaimer, el verdict rotulado como "Evaluación del motor", el bloque `self_eval`, y `R5_real_novel` mostrado como "real (sin precedente en el histórico)".

- [ ] **Step 1: Write the failing test** in `tests/test_certificate_render.py`:

```python
from src.certify.render import render_html


def _cert(rule="R1"):
    return {"schema": "mnemo.cert.v2", "attestation_type": "evidence_and_assessment",
            "disclaimer": "… no es una garantía …", "verdict": "apto-con-reservas", "risk_score": 10,
            "identity": {"project": "p", "commit_sha": "s", "run_id": "r", "created_at": "t",
                         "mnemo_version": "1.0", "model_version": "x"},
            "breakdown": {"real": 1}, "self_eval": {"confidence": "low",
                "engine_calibration": {"tenant_accuracy": 0.0, "n_corrections": 0}},
            "evidence": [{"failure_id": "f1", "category": "real", "confidence": 0.75,
                          "rule_applied": rule, "requires_approval": True}], "sign_offs": []}


def test_render_shows_disclaimer_and_assessment_label():
    out = render_html(_cert(), "SIG")
    assert "no es una garantía" in out.lower() or "garantía" in out.lower()
    assert "Evaluación del motor" in out
    assert "Veredicto:</strong>" not in out   # ya no se rotula como dictamen

def test_render_shows_self_eval_confidence():
    out = render_html(_cert(), "SIG")
    assert "low" in out.lower() and ("confianza" in out.lower())

def test_render_renames_real_novel():
    out = render_html(_cert(rule="R5_real_novel"), "SIG")
    assert "real (sin precedente en el histórico)" in out
    assert "R5_real_novel" not in out   # no se muestra el id crudo de la regla
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Implement** in `src/certify/render.py`. Add a rule-label helper and update `render_html` (keep `_e`/escaping). Replace the verdict line, add disclaimer + self_eval blocks, and use the label in the evidence rows:

```python
def _rule_label(rule: object) -> str:
    return "real (sin precedente en el histórico)" if rule == "R5_real_novel" else (str(rule) if rule is not None else "")
```

In `render_html`: the evidence rows use `_e(_rule_label(e.get('rule_applied')))` instead of `_e(e.get('rule_applied'))`; replace the `<strong>Veredicto:</strong>` line with `<strong>Evaluación del motor:</strong>`; after the identity block add a disclaimer paragraph `f"<p style='font-size:0.9em;color:#57606a'>{_e(cert.get('disclaimer'))}</p>"` and a self_eval block, e.g.:

```python
        se = cert.get("self_eval") or {}
        cal = se.get("engine_calibration", {})
        self_eval_html = (
            f"<h2>Auto-evaluación del motor</h2>"
            f"<p>Confianza: <strong>{_e(se.get('confidence'))}</strong> &middot; "
            f"precisión del motor en este cliente: {_e(cal.get('tenant_accuracy'))} "
            f"(n={_e(cal.get('n_corrections'))} correcciones)</p>"
        ) if se else ""
```
…and include `self_eval_html` + the disclaimer paragraph in the returned HTML.

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_certificate_render.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/certify/render.py tests/test_certificate_render.py
git commit -m "feat(cert): render como acta de evidencia (disclaimer + auto-evaluación + terminología honesta)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Schema v1→v2:** si algún test/consumidor afirmaba `schema == "mnemo.cert.v1"` o llamaba `build_certificate` sin `self_eval`, actualizarlo (el cert ahora exige `self_eval`). Buscar con `grep -rn "mnemo.cert.v1\|build_certificate" tests/ src/`.
- **cert↔gate:** ambos derivan `confidence` de `get_calibration_metrics` con el mismo mapeo → mismo veredicto para el mismo run (verificado por la consistencia de `compute_verdict`/`compute_confidence`, compartidas).
- **`save_certificate`** ya persiste el cert completo (`canonical_json=cert`), por lo que `self_eval` queda guardado y firmado sin cambios en el repo de certificados.
- **Fuera de alcance:** PR-2 (self-heal anti-enmascaramiento + higiene: modelo LLM + archivar RAG legacy).
