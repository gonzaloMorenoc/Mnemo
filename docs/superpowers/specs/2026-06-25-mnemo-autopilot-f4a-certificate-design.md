# Mnemo Autopilot — F4a: Release Assurance Certificate (diseño)

**Fecha:** 2026-06-25 · **Fase:** F4a (primera de F4, §7.2 del spec maestro) · **Rama:** `feat/mnemo-certificate` (desde `main`; autónoma sobre F2/F3a/F3b ya mergeadas)

## Objetivo

Generar, por run, un **Release Assurance Certificate** auditable y **firmado (Ed25519)**: JSON canónico con el veredicto (`apto`/`apto-con-reservas`/`no-apto`) + risk score + desglose por categoría + traza de evidencia, más render HTML y verificación de firma. Es el **entregable facturable** del producto. Determinista (no depende del LLM). El **gate** (check run) y RAGAS son fases/follow-ups posteriores.

## Decisiones (confirmadas)

- **Alcance: solo el certificado.** El gate (check run, depende de `GitHubCodeHost`/F3c) es **F4b**.
- **Determinista, sobre `triage_verdicts`.** El veredicto y el desglose se derivan de los veredictos de triaje del run (F2, en main) + el estado de las acciones (F3a/b, en main). No depende del LLM ni de F3c.
- **RAGAS diferido.** El JSON lleva un campo `self_eval` (objeto, `null` por defecto); la auto-evaluación RAGAS de la narrativa se integra en un follow-up (acoplarla rompería el determinismo del cert).
- **Render HTML** (no hay lib PDF en el repo). El endpoint de render sirve `text/html` imprimible; el PDF real es roadmap.
- **Append-only + RLS.** Tabla `certificates` inmutable (solo `select`/`insert`), con RLS `is_org_member` (invariante del proyecto).
- **Firma desprendida Ed25519** sobre el JSON canónico, clave en env (infra del cliente); `verify` solo necesita la pública.

## Componentes (`src/certify/`, archivos pequeños y puros)

### `signing.py`
- `canonical_json(cert: Dict) -> bytes` — `json.dumps(cert, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")` (determinista, estable ante orden de claves).
- `sign(canonical: bytes, private_key_pem: str) -> str` — Ed25519, firma → base64.
- `verify(canonical: bytes, signature_b64: str, public_key_pem: str) -> bool` — `try/except → False` (tamper-evident).
- Carga de claves desde env (`MNEMO_SIGNING_PRIVATE_KEY`, `MNEMO_SIGNING_PUBLIC_KEY`, PEM), perezosa. `SigningKeyMissing` si falta la privada al firmar.

### `certificate.py` (puro, núcleo del valor)
`build_certificate(*, run: Dict, verdicts: List[Dict], sign_offs: List[Dict], mnemo_version: str, model_version: str) -> Dict` → JSON canónico:
```json
{
  "schema": "mnemo.cert.v1",
  "identity": {"org_id","project","commit_sha","run_id","created_at","mnemo_version","model_version"},
  "verdict": "apto|apto-con-reservas|no-apto",
  "risk_score": 0-100,
  "breakdown": {"real": n, "flaky": n, "maintenance": n, "infra": n, "unknown": n},
  "evidence": [{"failure_id","test_name","category","confidence","rule_applied","requires_approval"}, ...],
  "sign_offs": [],
  "self_eval": null
}
```
- **Veredicto (política §7.1, determinista) — usa solo campos ya presentes en `triage_verdicts` (`category`, `requires_approval`, `rule_applied`), sin umbrales nuevos:**
  - `no-apto`: ≥1 veredicto `real` **novedoso** (`rule_applied == "R5_real_novel"`) con `requires_approval=false` (F2 lo dio por alta confianza), **o** ≥1 veredicto con `requires_approval=true` (pendiente de aprobación Nivel 2).
  - `apto-con-reservas`: no se cumple `no-apto`, pero hay ≥1 `real` (recurrente) o ≥1 `maintenance`.
  - `apto`: el resto (sin `real`; todo `flaky`/`maintenance`/`infra`/`unknown` reconocido).
- **`risk_score`** (0–100, determinista, fórmula fija): `min(100, 40*reales_novel_sin_approval + 20*pendientes_approval + 10*reales_recurrentes + 2*flaky)`.
- `created_at` se pasa como argumento (no se llama a `now()` dentro → función pura/testeable); lo inyecta `CertificateService.generate`.

### `render.py`
`render_html(cert: Dict) -> str` — HTML legible (template Python): identidad, veredicto + risk, desglose, tabla de evidencia, sign-offs, y la firma (truncada) + instrucciones de verificación. Puro.

### `repository.py` — `CertificateRepository`
Nueva clase (no engorda `defects/repository.py`). Patrón de `ActionRepository` (`_connect`/`_set_claims`, membership-gated):
- `save_certificate(*, user_id, org_id, run_id, canonical_json, signature, verdict, risk_score, sign_offs, mnemo_version, model_version) -> str` (id). Valida membership + que el run es del org.
- `get_certificate(*, user_id, run_id) -> Optional[Dict]` — el más reciente del run (membership-gated). None si no hay / no miembro.

### `service.py` — `CertificateService`
- `generate(*, user_id, run_id, created_at) -> Dict`: `repo.get_triage_for_run` (+ run info: org/project/commit_sha; `sign_offs=[]` en F4a) → `build_certificate` → `canonical_json` → `sign` → `save_certificate` → devuelve `{verdict, risk_score, artifact: {...}, signature}`. Si el run no tiene veredictos → `ValueError` (→422). Si falta la clave → `SigningKeyMissing` (→503).
- `get(*, user_id, run_id) -> Optional[Dict]`.

## Datos — migración `014_certificates.sql`

```sql
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
create index if not exists idx_certificates_run on public.certificates (run_id);
alter table public.certificates enable row level security;
alter table public.certificates force row level security;
drop policy if exists certificates_member on public.certificates;
create policy certificates_member on public.certificates for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert on public.certificates to authenticated;  -- append-only (sin update/delete)
```

## Endpoints (`/v2`, `Depends(get_current_user)`)

| Método | Ruta | Notas |
|---|---|---|
| POST | `/v2/certificates/run/{run_id}` | genera + firma + persiste (POST explícito, como `/propose`) |
| GET | `/v2/certificates/{run_id}` | el certificado del run (`canonical_json` + `signature` + `verdict` + `risk_score`) |
| GET | `/v2/certificates/{run_id}/html` | render HTML (`text/html`) |
| POST | `/v2/certificates/verify` | `{canonical_json, signature}` → `{valido: bool}` (auditor; usa la clave pública) |

Errores: 401 sin auth · no-miembro → vacío/403 · run sin veredictos → 422 · firma no configurada → 503 · `psycopg.Error` → 502.

## Config

`config.py`: `MNEMO_VERSION` (constante, p. ej. `"0.4.0"`), `MNEMO_SIGNING_PRIVATE_KEY`/`MNEMO_SIGNING_PUBLIC_KEY` (env, PEM). `model_version` del proveedor LLM configurado.

## Testing (TDD)

- **`signing`**: `sign`→`verify` OK; manipular el canonical → `verify` False (tamper-evident); `canonical_json` idéntico ante distinto orden de claves de entrada; clave ausente → `SigningKeyMissing`.
- **`certificate`** (puro): casos de veredicto — `no-apto` (real novedoso alta conf / pendiente de aprobación), `apto-con-reservas` (real resuelto + flaky), `apto` (todo flaky/infra); desglose y risk_score correctos; `created_at` inyectado.
- **`render`**: el HTML contiene veredicto, desglose, evidencia y la firma.
- **`CertificateRepository`** (integración Postgres): save→get; **append-only** (un `update`/`delete` por authenticated falla / no se expone método); aislamiento no-miembro → None; migración 014 (RLS + grants).
- **`CertificateService`** (mockeado): `generate` orquesta verdicts→build→sign→save; run sin veredictos → `ValueError`.
- **Endpoints**: 401 sin auth; generar→leer; `verify` OK y con firma manipulada → `{valido: false}`; 502 en error de BD; 503 sin clave.

## Fases (tareas del plan)

1. `signing.py` (canonical_json + sign/verify Ed25519 + carga de claves de env) + `MNEMO_VERSION`/claves en `config.py` + tests.
2. `certificate.py` (`build_certificate`: veredicto/risk/desglose/evidencia, puro) + tests de casos.
3. `render.py` (`render_html`) + tests.
4. Migración `014` + `CertificateRepository` (save/get, append-only, RLS) + tests integración.
5. `CertificateService` (generate/get) + endpoints `/v2/certificates*` + wiring en `api_v2` + tests de endpoint.

## Fuera de alcance (YAGNI / fases posteriores)

- **Gate / check run** (`mnemo/assurance` success|failure|neutral, política bloquea/aprueba, `GitHubCodeHost.publish_check_run`) → **F4b** (depende de F3c).
- **RAGAS** (`self_eval`) · **PDF** real (hoy HTML) · sign-offs ricos (vincular cada aprobación de baja confianza) · **F5** (lazo de aprendizaje + frontend) · **F6** (demo).
