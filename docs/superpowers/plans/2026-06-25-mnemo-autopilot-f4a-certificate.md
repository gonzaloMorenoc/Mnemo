# F4a — Release Assurance Certificate — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generar, por run, un Release Assurance Certificate determinista y firmado (Ed25519) — veredicto + risk score + desglose + evidencia — con render HTML y verificación de firma.

**Architecture:** `src/certify/` con funciones puras (`signing`, `certificate`, `render`) + `CertificateRepository` (append-only) + `CertificateService`. El veredicto se deriva de los `triage_verdicts` del run (F2, en main). Firma desprendida Ed25519 sobre el JSON canónico. Sin LLM (determinista).

**Tech Stack:** Python 3.13, FastAPI, psycopg, `cryptography` (Ed25519, ya en requirements), pytest (+ `@pytest.mark.integration` para Postgres).

## Global Constraints

- **Determinista:** `build_certificate` es puro; `created_at` se inyecta (no `now()` dentro). Sin LLM.
- **Firma:** `canonical_json = json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`; firma Ed25519 desprendida en base64; tamper-evident.
- **Veredicto (sobre `triage_verdicts`, sin umbrales nuevos):** `no-apto` si ≥1 `real` novedoso (`rule_applied=="R5_real_novel"`) con `requires_approval=false`, **o** ≥1 con `requires_approval=true`; `apto-con-reservas` si no es `no-apto` pero hay `real`/`flaky`/`maintenance`; `apto` el resto.
- **`risk_score`** (0–100): `min(100, 40*reales_novel_sin_approval + 20*pendientes_approval + 10*reales_recurrentes + 2*flaky)`.
- **Aislamiento multitenant:** cada método de repo valida membership (`exists(memberships)`). El pooler bypasea RLS.
- **Invariante RLS:** la tabla nueva lleva `enable`+`force`+policy `is_org_member(org_id)`; append-only = `grant select, insert` (sin update/delete).
- **Errores `/v2`:** 401 sin auth · `PermissionError`→403 / vacío · `ValueError`→422 (run sin veredictos) · `SigningKeyMissing`→503 · `psycopg.Error`→502.
- `DATABASE_URL` (.env) **es producción**: aplicar la migración 014 con `psql` (Bash con `dangerouslyDisableSandbox` por la red); los tests de integración corren contra esa BD (con cleanup en fixtures).
- Commits `feat:`/`test:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`. Tests con `python3 -m pytest`.

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `src/config.py` | modificar | `MNEMO_VERSION`, `MNEMO_SIGNING_PRIVATE_KEY`, `MNEMO_SIGNING_PUBLIC_KEY` |
| `src/certify/__init__.py` | crear | paquete |
| `src/certify/signing.py` | crear | `canonical_json` + `sign`/`verify` Ed25519 + `SigningKeyMissing` |
| `src/certify/certificate.py` | crear | `build_certificate` (puro) |
| `src/certify/render.py` | crear | `render_html` |
| `src/certify/repository.py` | crear | `CertificateRepository` (get_run_meta, save, get) |
| `src/certify/service.py` | crear | `CertificateService` (generate/get) |
| `db/migrations/014_certificates.sql` | crear | tabla `certificates` append-only + RLS |
| `src/multitenant_models.py` | modificar | modelos de request/response |
| `src/api_v2.py` | modificar | getters + endpoints `/v2/certificates*` |
| `tests/test_certify_signing.py` | crear | Ed25519 (cryptography real) |
| `tests/test_certify_certificate.py` | crear | casos de veredicto/risk/desglose |
| `tests/test_certify_render.py` | crear | HTML |
| `tests/test_certify_repository.py` | crear | integración Postgres |
| `tests/test_api_v2_certificates.py` | crear | endpoints |

---

## Task 1: `signing.py` + config

**Files:**
- Create: `src/certify/__init__.py` (vacío), `src/certify/signing.py`
- Modify: `src/config.py`
- Test: `tests/test_certify_signing.py`

**Interfaces:**
- Produces: `canonical_json(cert: Dict) -> bytes`; `sign(canonical: bytes, private_key_pem: str) -> str`; `verify(canonical: bytes, signature_b64: str, public_key_pem: str) -> bool`; `SigningKeyMissing(RuntimeError)`. Config: `MNEMO_VERSION: str`, `MNEMO_SIGNING_PRIVATE_KEY: str`, `MNEMO_SIGNING_PUBLIC_KEY: str`.

- [ ] **Step 1: Config**

In `src/config.py`, add near the other `os.getenv` lines:

```python
MNEMO_VERSION = "0.4.0"
MNEMO_SIGNING_PRIVATE_KEY = os.getenv("MNEMO_SIGNING_PRIVATE_KEY", "")
MNEMO_SIGNING_PUBLIC_KEY = os.getenv("MNEMO_SIGNING_PUBLIC_KEY", "")
```

- [ ] **Step 2: Write the failing tests** in `tests/test_certify_signing.py`:

```python
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.certify.signing import canonical_json, sign, verify, SigningKeyMissing


def _keypair():
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


def test_canonical_json_is_key_order_stable():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_sign_then_verify_ok():
    priv, pub = _keypair()
    canonical = canonical_json({"verdict": "apto", "risk_score": 0})
    assert verify(canonical, sign(canonical, priv), pub) is True


def test_verify_fails_on_tamper():
    priv, pub = _keypair()
    sig = sign(canonical_json({"verdict": "apto"}), priv)
    assert verify(canonical_json({"verdict": "no-apto"}), sig, pub) is False


def test_verify_fails_on_bad_signature():
    _, pub = _keypair()
    assert verify(canonical_json({"a": 1}), "bm90LWEtc2ln", pub) is False


def test_sign_without_key_raises():
    with pytest.raises(SigningKeyMissing):
        sign(b"x", "")
```

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_certify_signing.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement** `src/certify/signing.py`:

```python
import base64
import json
from typing import Any, Dict

from cryptography.hazmat.primitives import serialization


class SigningKeyMissing(RuntimeError):
    """La clave privada de firma (MNEMO_SIGNING_PRIVATE_KEY) no está configurada."""


def canonical_json(cert: Dict[str, Any]) -> bytes:
    """Serialización canónica determinista: claves ordenadas, sin espacios, UTF-8."""
    return json.dumps(cert, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign(canonical: bytes, private_key_pem: str) -> str:
    if not private_key_pem:
        raise SigningKeyMissing("MNEMO_SIGNING_PRIVATE_KEY no configurada")
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    return base64.b64encode(key.sign(canonical)).decode("ascii")


def verify(canonical: bytes, signature_b64: str, public_key_pem: str) -> bool:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        key.verify(base64.b64decode(signature_b64), canonical)
        return True
    except Exception:  # noqa: BLE001 — verificación booleana, cualquier fallo → False
        return False
```

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_certify_signing.py -q` → PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add src/config.py src/certify/__init__.py src/certify/signing.py tests/test_certify_signing.py
git commit -m "feat(certify): firma Ed25519 + JSON canónico + config de claves

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `certificate.py` — `build_certificate` (puro)

**Files:**
- Create: `src/certify/certificate.py`
- Test: `tests/test_certify_certificate.py`

**Interfaces:**
- Consumes: veredictos con forma de `get_triage_for_run` (`{id, failure_id, category, confidence, rule_applied, evidence_bundle, requires_approval, llm_assisted, status}`).
- Produces: `build_certificate(*, run: Dict, verdicts: List[Dict], sign_offs: List[Dict], mnemo_version: str, model_version: str, created_at: str) -> Dict`. `run` = `{org_id, project, commit_sha, run_id}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_certify_certificate.py`:

```python
from src.certify.certificate import build_certificate

_RUN = {"org_id": "o", "project": "web", "commit_sha": "abc123", "run_id": "r1"}


def _v(category, *, rule="", approval=False, conf=0.9, fid="f1"):
    return {"id": "v", "failure_id": fid, "category": category, "confidence": conf,
            "rule_applied": rule, "evidence_bundle": {}, "requires_approval": approval,
            "llm_assisted": False, "status": "resolved"}


def _cert(verdicts):
    return build_certificate(run=_RUN, verdicts=verdicts, sign_offs=[],
                             mnemo_version="0.4.0", model_version="llama3", created_at="2026-06-25T00:00:00Z")


def test_no_apto_on_novel_real_high_confidence():
    c = _cert([_v("real", rule="R5_real_novel", approval=False)])
    assert c["verdict"] == "no-apto"


def test_no_apto_on_pending_approval():
    c = _cert([_v("flaky", approval=True)])
    assert c["verdict"] == "no-apto"


def test_apto_con_reservas_on_recurrent_real():
    c = _cert([_v("real", rule="R4_real_recurrent", approval=False)])
    assert c["verdict"] == "apto-con-reservas"


def test_apto_when_all_flaky_or_infra():
    c = _cert([_v("flaky"), _v("infra")])
    assert c["verdict"] == "apto"


def test_breakdown_and_identity_and_evidence():
    c = _cert([_v("real", rule="R4_real_recurrent", fid="fa"), _v("flaky", fid="fb")])
    assert c["breakdown"]["real"] == 1 and c["breakdown"]["flaky"] == 1
    assert c["identity"]["commit_sha"] == "abc123" and c["identity"]["mnemo_version"] == "0.4.0"
    assert c["schema"] == "mnemo.cert.v1" and c["sign_offs"] == [] and c["self_eval"] is None
    assert {e["failure_id"] for e in c["evidence"]} == {"fa", "fb"}


def test_risk_score_formula():
    # 1 novel-sin-approval (40) + 1 pendiente (20) + 1 recurrente (10) + 1 flaky (2) = 72
    c = _cert([_v("real", rule="R5_real_novel"), _v("infra", approval=True),
               _v("real", rule="R4_real_recurrent"), _v("flaky")])
    assert c["risk_score"] == 72
    assert c["verdict"] == "no-apto"  # hay novel-sin-approval y pendiente
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_certify_certificate.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `src/certify/certificate.py`:

```python
from typing import Any, Dict, List

_CATEGORIES = ("real", "flaky", "maintenance", "infra", "unknown")


def build_certificate(*, run: Dict[str, Any], verdicts: List[Dict[str, Any]],
                      sign_offs: List[Dict[str, Any]], mnemo_version: str,
                      model_version: str, created_at: str) -> Dict[str, Any]:
    """Certificado determinista de un run a partir de sus veredictos de triaje.
    Puro: el timestamp se inyecta (created_at)."""
    breakdown = {c: 0 for c in _CATEGORIES}
    for v in verdicts:
        cat = v.get("category") or "unknown"
        breakdown[cat] = breakdown.get(cat, 0) + 1

    reales_novel_sin_approval = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") == "R5_real_novel" and not v.get("requires_approval"))
    pendientes_approval = sum(1 for v in verdicts if v.get("requires_approval"))
    reales_recurrentes = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") != "R5_real_novel")
    flaky = breakdown["flaky"]

    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        verdict = "no-apto"
    elif breakdown["real"] > 0 or breakdown["flaky"] > 0 or breakdown["maintenance"] > 0:
        verdict = "apto-con-reservas"
    else:
        verdict = "apto"

    risk_score = min(100, 40 * reales_novel_sin_approval + 20 * pendientes_approval
                     + 10 * reales_recurrentes + 2 * flaky)

    evidence = [
        {"failure_id": v.get("failure_id"), "category": v.get("category"),
         "confidence": v.get("confidence"), "rule_applied": v.get("rule_applied"),
         "requires_approval": v.get("requires_approval")}
        for v in verdicts
    ]
    return {
        "schema": "mnemo.cert.v1",
        "identity": {"org_id": run["org_id"], "project": run["project"],
                     "commit_sha": run.get("commit_sha"), "run_id": run["run_id"],
                     "created_at": created_at, "mnemo_version": mnemo_version,
                     "model_version": model_version},
        "verdict": verdict,
        "risk_score": risk_score,
        "breakdown": breakdown,
        "evidence": evidence,
        "sign_offs": sign_offs,
        "self_eval": None,
    }
```

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_certify_certificate.py -q` → PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/certify/certificate.py tests/test_certify_certificate.py
git commit -m "feat(certify): build_certificate determinista (veredicto/risk/desglose/evidencia)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: `render.py` — `render_html`

**Files:**
- Create: `src/certify/render.py`
- Test: `tests/test_certify_render.py`

**Interfaces:**
- Consumes: el dict de `build_certificate`.
- Produces: `render_html(cert: Dict, signature: str) -> str`.

- [ ] **Step 1: Write the failing test** in `tests/test_certify_render.py`:

```python
from src.certify.render import render_html

_CERT = {
    "schema": "mnemo.cert.v1",
    "identity": {"org_id": "o", "project": "web", "commit_sha": "abc123",
                 "run_id": "r1", "created_at": "2026-06-25T00:00:00Z",
                 "mnemo_version": "0.4.0", "model_version": "llama3"},
    "verdict": "no-apto", "risk_score": 72,
    "breakdown": {"real": 2, "flaky": 1, "maintenance": 0, "infra": 0, "unknown": 0},
    "evidence": [{"failure_id": "fa", "category": "real", "confidence": 0.9,
                  "rule_applied": "R5_real_novel", "requires_approval": False}],
    "sign_offs": [], "self_eval": None,
}


def test_render_contains_key_fields():
    html = render_html(_CERT, "sig-b64")
    assert "<html" in html.lower()
    assert "no-apto" in html and "72" in html
    assert "web" in html and "abc123" in html
    assert "real" in html and "fa" in html
    assert "sig-b64" in html


def test_render_escapes_nothing_breaks_on_empty_evidence():
    cert = {**_CERT, "evidence": [], "verdict": "apto", "risk_score": 0}
    html = render_html(cert, "s")
    assert "apto" in html
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_certify_render.py -q` → FAIL.

- [ ] **Step 3: Implement** `src/certify/render.py`:

```python
from typing import Any, Dict

_VERDICT_COLOR = {"apto": "#1a7f37", "apto-con-reservas": "#9a6700", "no-apto": "#cf222e"}


def render_html(cert: Dict[str, Any], signature: str) -> str:
    idn = cert.get("identity", {})
    bd = cert.get("breakdown", {})
    color = _VERDICT_COLOR.get(cert.get("verdict", ""), "#57606a")
    rows = "".join(
        f"<tr><td>{e.get('failure_id')}</td><td>{e.get('category')}</td>"
        f"<td>{e.get('confidence')}</td><td>{e.get('rule_applied')}</td>"
        f"<td>{'sí' if e.get('requires_approval') else 'no'}</td></tr>"
        for e in cert.get("evidence", [])
    )
    breakdown = ", ".join(f"{k}: {v}" for k, v in bd.items())
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Release Assurance Certificate</title></head><body>"
        "<h1>Release Assurance Certificate</h1>"
        f"<p><strong>Veredicto:</strong> <span style='color:{color}'>{cert.get('verdict')}</span>"
        f" &middot; <strong>Risk score:</strong> {cert.get('risk_score')}</p>"
        f"<p>Proyecto <code>{idn.get('project')}</code> &middot; commit <code>{idn.get('commit_sha')}</code>"
        f" &middot; run <code>{idn.get('run_id')}</code> &middot; {idn.get('created_at')}</p>"
        f"<p>Mnemo {idn.get('mnemo_version')} &middot; modelo {idn.get('model_version')}</p>"
        f"<p><strong>Desglose:</strong> {breakdown}</p>"
        "<h2>Evidencia</h2><table border='1' cellpadding='4'>"
        "<tr><th>failure_id</th><th>categoría</th><th>confianza</th><th>regla</th><th>req. aprobación</th></tr>"
        f"{rows}</table>"
        f"<h2>Firma (Ed25519)</h2><pre style='white-space:pre-wrap'>{signature}</pre>"
        "<p>Verificable con <code>POST /v2/certificates/verify</code> y la clave pública.</p>"
        "</body></html>"
    )
```

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_certify_render.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/certify/render.py tests/test_certify_render.py
git commit -m "feat(certify): render_html del certificado

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 4: Migración 014 + `CertificateRepository`

**Files:**
- Create: `db/migrations/014_certificates.sql`, `src/certify/repository.py`
- Test: `tests/test_certify_repository.py`

**Interfaces:**
- Produces: `CertificateRepository(db_url=DATABASE_URL)` con:
  - `get_run_meta(*, user_id, run_id) -> Optional[Dict]` → `{org_id, project, commit_sha}` (membership-gated, None si no miembro/no existe).
  - `save_certificate(*, user_id, org_id, run_id, canonical_json, signature, verdict, risk_score, sign_offs, mnemo_version, model_version) -> str` (id).
  - `get_certificate(*, user_id, run_id) -> Optional[Dict]` → `{id, run_id, org_id, canonical_json, signature, verdict, risk_score, sign_offs, mnemo_version, model_version, created_at}` (el más reciente del run).

- [ ] **Step 1: Migración**

Create `db/migrations/014_certificates.sql`:

```sql
-- db/migrations/014_certificates.sql
-- Mnemo Autopilot F4a: Release Assurance Certificate (append-only, firmado).

create table if not exists public.certificates (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    canonical_json jsonb not null,
    signature text not null,
    verdict text not null check (verdict in ('apto', 'apto-con-reservas', 'no-apto')),
    risk_score int not null,
    sign_offs jsonb,
    mnemo_version text,
    model_version text,
    created_at timestamptz not null default now()
);
create index if not exists idx_certificates_run on public.certificates (run_id, created_at desc);

alter table public.certificates enable row level security;
alter table public.certificates force row level security;
drop policy if exists certificates_member on public.certificates;
create policy certificates_member on public.certificates for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert on public.certificates to authenticated;  -- append-only
```

Aplicar a la BD (es producción): `set -a && source .env && set +a && psql "$DATABASE_URL" -f db/migrations/014_certificates.sql` (Bash con `dangerouslyDisableSandbox`).

- [ ] **Step 2: Write the failing integration test** in `tests/test_certify_repository.py`:

```python
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.certify.repository import CertificateRepository
from src.defects.repository import AssuranceRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def repos():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return CertificateRepository(DBURL), AssuranceRepository(DBURL)


@pytest.fixture
def org():
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"cert-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("cert-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
            cur.execute("insert into public.test_runs (org_id, project, source, commit_sha)"
                        " values (%s, 'web', 'playwright', 'sha-cert') returning id", (org_id,))
            run_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id, "run_id": run_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def test_get_run_meta(repos, org):
    crepo, _ = repos
    meta = crepo.get_run_meta(user_id=org["user_id"], run_id=org["run_id"])
    assert meta == {"org_id": org["org_id"], "project": "web", "commit_sha": "sha-cert"}
    assert crepo.get_run_meta(user_id=str(uuid.uuid4()), run_id=org["run_id"]) is None  # no-miembro


def test_save_then_get_certificate(repos, org):
    crepo, _ = repos
    u, o, r = org["user_id"], org["org_id"], org["run_id"]
    cid = crepo.save_certificate(user_id=u, org_id=o, run_id=r,
                                 canonical_json={"verdict": "apto"}, signature="sig",
                                 verdict="apto", risk_score=0, sign_offs=[],
                                 mnemo_version="0.4.0", model_version="llama3")
    assert cid
    got = crepo.get_certificate(user_id=u, run_id=r)
    assert got["verdict"] == "apto" and got["signature"] == "sig" and got["canonical_json"] == {"verdict": "apto"}
    assert crepo.get_certificate(user_id=str(uuid.uuid4()), run_id=r) is None  # no-miembro


def test_save_certificate_non_member_rejected(repos, org):
    crepo, _ = repos
    with pytest.raises((PermissionError, ValueError)):
        crepo.save_certificate(user_id=str(uuid.uuid4()), org_id=org["org_id"], run_id=org["run_id"],
                               canonical_json={}, signature="s", verdict="apto", risk_score=0,
                               sign_offs=[], mnemo_version="v", model_version="m")
```

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_certify_repository.py -q` → FAIL (`ModuleNotFoundError`). (Needs DB + migration 014 applied.)

- [ ] **Step 4: Implement** `src/certify/repository.py`:

```python
from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.config import DATABASE_URL


class CertificateRepository:
    """Acceso a datos de certificados (append-only). El pooler bypasea RLS → membership
    en la capa de app en cada método."""

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.db_url, row_factory=dict_row)

    def _set_claims(self, conn: psycopg.Connection, user_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def get_run_meta(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select r.org_id, r.project, r.commit_sha from public.test_runs r"
                    " where r.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (run_id, user_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"org_id": str(row["org_id"]), "project": row["project"],
                "commit_sha": row["commit_sha"]}

    def save_certificate(self, *, user_id: str, org_id: str, run_id: str,
                         canonical_json: Dict[str, Any], signature: str, verdict: str,
                         risk_score: int, sign_offs: Any, mnemo_version: str,
                         model_version: str) -> str:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute("select 1 from public.test_runs where id = %s and org_id = %s",
                            (run_id, org_id))
                if cur.fetchone() is None:
                    raise ValueError("run does not belong to the organization")
                cur.execute(
                    "insert into public.certificates"
                    " (run_id, org_id, canonical_json, signature, verdict, risk_score,"
                    "  sign_offs, mnemo_version, model_version)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                    (run_id, org_id, Json(canonical_json), signature, verdict, risk_score,
                     Json(sign_offs), mnemo_version, model_version),
                )
                cid = str(cur.fetchone()["id"])
            conn.commit()
        return cid

    def get_certificate(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select c.id, c.run_id, c.org_id, c.canonical_json, c.signature, c.verdict,"
                    "       c.risk_score, c.sign_offs, c.mnemo_version, c.model_version, c.created_at"
                    " from public.certificates c"
                    " where c.run_id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = c.org_id and m.user_id = %s)"
                    " order by c.created_at desc limit 1",
                    (run_id, user_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"id": str(row["id"]), "run_id": str(row["run_id"]), "org_id": str(row["org_id"]),
                "canonical_json": row["canonical_json"], "signature": row["signature"],
                "verdict": row["verdict"], "risk_score": row["risk_score"],
                "sign_offs": row["sign_offs"], "mnemo_version": row["mnemo_version"],
                "model_version": row["model_version"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None}
```

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_certify_repository.py -q` → PASS (3 passed; needs DB + migration 014).

- [ ] **Step 6: Commit**

```bash
git add db/migrations/014_certificates.sql src/certify/repository.py tests/test_certify_repository.py
git commit -m "feat(certify): migración 014 (certificates append-only + RLS) + CertificateRepository

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 5: `CertificateService` + endpoints + wiring

**Files:**
- Create: `src/certify/service.py`
- Modify: `src/multitenant_models.py`, `src/api_v2.py`
- Test: `tests/test_api_v2_certificates.py`

**Interfaces:**
- Consumes: `AssuranceRepository.get_triage_for_run` (veredictos), `CertificateRepository` (Task 4), `build_certificate` (Task 2), `canonical_json`/`sign`/`verify` (Task 1), `render_html` (Task 3).
- Produces: `CertificateService(*, repo, cert_repo, private_key, public_key, mnemo_version, model_version)` con `generate(*, user_id, run_id, created_at) -> Dict` y `get(*, user_id, run_id) -> Optional[Dict]`. Endpoints `/v2/certificates*`.

- [ ] **Step 1: Models** in `src/multitenant_models.py` (junto a los demás):

```python
class CertificateResponse(BaseModel):
    run_id: str
    verdict: str
    risk_score: int
    canonical_json: dict
    signature: str
    created_at: Optional[str] = None


class CertificateVerifyRequest(BaseModel):
    canonical_json: dict
    signature: str


class CertificateVerifyResponse(BaseModel):
    valido: bool
```

- [ ] **Step 2: Implement** `src/certify/service.py`:

```python
from typing import Any, Dict, Optional

from src.certify.certificate import build_certificate
from src.certify.signing import canonical_json, sign


class CertificateService:
    """Genera y recupera Release Assurance Certificates. Determinista; firma Ed25519."""

    def __init__(self, *, repo, cert_repo, private_key: str, public_key: str,
                 mnemo_version: str, model_version: str):
        self.repo = repo               # AssuranceRepository (get_triage_for_run)
        self.cert_repo = cert_repo     # CertificateRepository
        self._private_key = private_key
        self._public_key = public_key
        self._mnemo_version = mnemo_version
        self._model_version = model_version

    def generate(self, *, user_id: str, run_id: str, created_at: str) -> Dict[str, Any]:
        meta = self.cert_repo.get_run_meta(user_id=user_id, run_id=run_id)
        if meta is None:
            raise ValueError("run no encontrado o sin acceso")
        verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
        if not verdicts:
            raise ValueError("run sin veredictos de triaje")
        cert = build_certificate(
            run={"org_id": meta["org_id"], "project": meta["project"],
                 "commit_sha": meta["commit_sha"], "run_id": run_id},
            verdicts=verdicts, sign_offs=[], mnemo_version=self._mnemo_version,
            model_version=self._model_version, created_at=created_at,
        )
        canonical = canonical_json(cert)
        signature = sign(canonical, self._private_key)  # SigningKeyMissing si falta
        self.cert_repo.save_certificate(
            user_id=user_id, org_id=meta["org_id"], run_id=run_id, canonical_json=cert,
            signature=signature, verdict=cert["verdict"], risk_score=cert["risk_score"],
            sign_offs=cert["sign_offs"], mnemo_version=self._mnemo_version,
            model_version=self._model_version,
        )
        return {"run_id": run_id, "verdict": cert["verdict"], "risk_score": cert["risk_score"],
                "canonical_json": cert, "signature": signature, "created_at": created_at}

    def get(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        return self.cert_repo.get_certificate(user_id=user_id, run_id=run_id)
```

- [ ] **Step 3: Write the failing endpoint tests** in `tests/test_api_v2_certificates.py`:

```python
from unittest.mock import MagicMock

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if service is not None:
        app.dependency_overrides[api_v2.get_certificate_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_generate_returns_certificate():
    svc = MagicMock()
    svc.generate.return_value = {"run_id": "r1", "verdict": "apto", "risk_score": 0,
                                 "canonical_json": {"verdict": "apto"}, "signature": "sig",
                                 "created_at": "2026-06-25T00:00:00Z"}
    resp = _client(service=svc).post("/v2/certificates/run/r1")
    assert resp.status_code == 200 and resp.json()["verdict"] == "apto"


def test_generate_run_without_verdicts_is_422():
    svc = MagicMock()
    svc.generate.side_effect = ValueError("run sin veredictos de triaje")
    assert _client(service=svc).post("/v2/certificates/run/r1").status_code == 422


def test_generate_missing_key_is_503():
    from src.certify.signing import SigningKeyMissing
    svc = MagicMock()
    svc.generate.side_effect = SigningKeyMissing("no key")
    assert _client(service=svc).post("/v2/certificates/run/r1").status_code == 503


def test_get_certificate_404_when_absent():
    svc = MagicMock()
    svc.get.return_value = None
    assert _client(service=svc).get("/v2/certificates/r1").status_code == 404


def test_get_certificate_html():
    svc = MagicMock()
    svc.get.return_value = {
        "run_id": "r1", "verdict": "apto", "risk_score": 0, "signature": "sig",
        "canonical_json": {"verdict": "apto", "identity": {}, "breakdown": {}, "evidence": []},
        "created_at": "2026-06-25T00:00:00Z"}
    resp = _client(service=svc).get("/v2/certificates/r1/html")
    assert resp.status_code == 200 and "apto" in resp.text


def test_verify_endpoint_roundtrip():
    from src.certify.signing import canonical_json, sign, verify
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    cert = {"verdict": "apto"}
    sig = sign(canonical_json(cert), priv_pem)
    svc = MagicMock()
    svc.verify_payload.return_value = verify(canonical_json(cert), sig, pub_pem)
    resp = _client(service=svc).post("/v2/certificates/verify",
                                     json={"canonical_json": cert, "signature": sig})
    assert resp.status_code == 200 and resp.json()["valido"] is True


def test_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/certificates/run/r1").status_code == 401
```

- [ ] **Step 4: Run, expect FAIL**

Run: `python3 -m pytest tests/test_api_v2_certificates.py -q` → FAIL (no endpoints / `get_certificate_service`).

- [ ] **Step 5: Wire `api_v2.py`**.

Add imports (junto a los otros):

```python
from src.certify.repository import CertificateRepository
from src.certify.service import CertificateService
from src.certify.signing import SigningKeyMissing, canonical_json, verify
from src.config import MNEMO_VERSION, MNEMO_SIGNING_PRIVATE_KEY, MNEMO_SIGNING_PUBLIC_KEY, LLM_MODEL
from src.multitenant_models import (CertificateResponse, CertificateVerifyRequest,
                                    CertificateVerifyResponse)
```

Add singleton + getter (junto a `get_action_service`); `_cert_repo`/`_certificate_service` globals next to the others:

```python
_cert_repo = None
_certificate_service = None


def get_certificate_service() -> CertificateService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _cert_repo, _certificate_service
    if _certificate_service is None:
        _cert_repo = CertificateRepository()
        _certificate_service = CertificateService(
            repo=get_assurance_repo(), cert_repo=_cert_repo,
            private_key=MNEMO_SIGNING_PRIVATE_KEY, public_key=MNEMO_SIGNING_PUBLIC_KEY,
            mnemo_version=MNEMO_VERSION, model_version=LLM_MODEL or "unknown",
        )
    return _certificate_service
```

Add a `verify_payload` method to `CertificateService` (in `src/certify/service.py`) — the verify endpoint uses the configured public key:

```python
    def verify_payload(self, *, cert: Dict[str, Any], signature: str) -> bool:
        from src.certify.signing import verify as _verify
        return _verify(canonical_json(cert), signature, self._public_key)
```

Add endpoints (use a passed-in timestamp; FastAPI can read it server-side):

```python
from datetime import datetime, timezone


@router.post("/certificates/run/{run_id}", response_model=CertificateResponse)
def generate_certificate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        return CertificateResponse(**service.generate(user_id=user.user_id, run_id=run_id,
                                                      created_at=created_at))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SigningKeyMissing as exc:
        raise HTTPException(status_code=503, detail="Firma no configurada") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.get("/certificates/{run_id}", response_model=CertificateResponse)
def get_certificate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    try:
        cert = service.get(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if cert is None:
        raise HTTPException(status_code=404, detail="certificate not found")
    return CertificateResponse(run_id=cert["run_id"], verdict=cert["verdict"],
                               risk_score=cert["risk_score"], canonical_json=cert["canonical_json"],
                               signature=cert["signature"], created_at=cert["created_at"])


@router.post("/certificates/verify", response_model=CertificateVerifyResponse)
def verify_certificate_v2(
    body: CertificateVerifyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateVerifyResponse:
    return CertificateVerifyResponse(
        valido=service.verify_payload(cert=body.canonical_json, signature=body.signature))
```

HTML endpoint (add `from fastapi.responses import HTMLResponse` and `from src.certify.render import render_html` to the imports):

```python
@router.get("/certificates/{run_id}/html", response_class=HTMLResponse)
def get_certificate_html_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> HTMLResponse:
    try:
        cert = service.get(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if cert is None:
        raise HTTPException(status_code=404, detail="certificate not found")
    return HTMLResponse(render_html(cert["canonical_json"], cert["signature"]))
```

- [ ] **Step 6: Run, expect PASS**

Run: `python3 -m pytest tests/test_api_v2_certificates.py -q` → PASS.

- [ ] **Step 7: Full suite + commit**

Run: `python3 -m pytest -m "not integration" -q` → green. Then:

```bash
git add src/certify/service.py src/multitenant_models.py src/api_v2.py tests/test_api_v2_certificates.py
git commit -m "feat(certify): CertificateService + endpoints /v2/certificates (generar/leer/html/verify)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Despliegue:** aplicar `db/migrations/014_certificates.sql`; configurar `MNEMO_SIGNING_PRIVATE_KEY`/`_PUBLIC_KEY` (Ed25519 PEM) en el backend.
- **Diferencia con el spec:** la evidencia del cert usa `failure_id` (no `test_name`) para no tocar `get_triage_for_run` ni a sus consumidores de F2; añadir `test_name` es un follow-up (extender ese método con un join a `failures`).
- **Fuera de alcance:** el **gate** (check run, F4b, depende de F3c), **RAGAS** (`self_eval`), **PDF** real, sign-offs poblados.
