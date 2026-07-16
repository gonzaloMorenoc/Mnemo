# Mnemo — Arquitectura técnica

## Visión: QA Continuity AI

Mnemo es una plataforma de **continuidad operativa de QA**: captura la memoria del equipo (patrones de defecto, conocimiento de dominio, decisiones pasadas) y la usa para acelerar el trabajo de QA del día a día. El lazo Autopilot (triaje → acción → certificado) es la **fuente principal de datos** que alimenta la memoria, no el centro del producto.

## Stack

- **Backend:** Python 3.13, FastAPI. **Embeddings locales**: `all-MiniLM-L6-v2` (384 dims, CPU) vía HuggingFace. **LLM intercambiable** (`src/llm/factory.py`): Ollama (`qwen3:8b`, default de código — local, 0 €, data-residency), cualquier API compatible OpenAI vía `OPENAI_BASE_URL` (el deploy de demo usa **Gemini free tier**), o Anthropic. Los proveedores externos exigen opt-in explícito (`ALLOW_EXTERNAL_LLM=true`) porque envían datos de fallos a un tercero.
- **Datos:** **Postgres + pgvector** (Supabase). Auth: **Supabase JWT** (verificación por JWKS).
- **Frontend:** Next.js (App Router) + React + TypeScript + TanStack Query + shadcn/ui; auth Supabase.

## Capas

```
  Frontend Next.js
  (público: /verify · app: /app/{assurance,autopilot,calibration,defects,graph,
   integrations,knowledge,onboarding,org,settings,test-plan})
                       │  (proxy /api/v2/* → backend /v2/*)
                       ▼
   FastAPI  asgi.py ──include──►  src/api_v2.py  (router /v2, auth JWT, deps perezosas)
                       │
      ┌────────────────┼──────────────────────────────────────────────┐
      ▼                ▼                    ▼                          ▼
  Ingest+Triage    Knowledge+Graph      TestPlan+Xray         Automation+CI+Repo
  (src/ingest/     (src/knowledge/      (src/testplan/        (src/automation/
   src/defects/     src/graph/)          src/xray/)            src/ci/
   src/triage/                                                 src/repo_ingest/)
   src/actions/
   src/certify/)
      │                │                    │                          │
  Postgres+pgvector   Postgres+pgvector   LLM provider          GitHub App
  LLM provider (perezoso)  LLM provider   Xray API
```

## Módulos de capacidad

| Módulo | Ruta | Responsabilidad |
|--------|------|-----------------|
| **Ingest** | `src/ingest/` | Parsers de **7 formatos** de report (Allure, JUnit, TestNG, Robot, Playwright, Cypress, Cucumber) + autodetección (`detect.py`), modelos, red de seguridad anti-falso-verde |
| **Defects / Defect DNA** | `src/defects/` | AssuranceRepository, fingerprint, embedder, match, centroid, IngestionService; `src/assurance/`: verdict + narrator |
| **Triage** | `src/triage/` | Motor de reglas R0–R6 (determinista) + `LLMTiebreaker` para ambiguos (`llm_assisted`) |
| **Actions** | `src/actions/` | ActionService + ActionRepository: propone y materializa acciones (quarantine/ticket/self_heal) |
| **Certify** | `src/certify/` | Certificados firmados **Ed25519** + verificación; GateService |
| **Knowledge** | `src/knowledge/` | QaKnowledgeRepository + KnowledgeService: memoria RAG de QA (7 kinds) |
| **Graph** | `src/graph/` | GraphService: grafo de conocimiento (dominios → familias → ítems); `gaps.py`: huecos de cobertura cruzando memoria × test assets |
| **TestPlan** | `src/testplan/` | Generación de planes de prueba desde HUs; `src/xray/`: exportación a Jira/Xray |
| **Automation** | `src/automation/` | Generación de tests Playwright (.spec.ts); estilo few-shot desde los test assets del repo |
| **Repo ingest** | `src/repo_ingest/` | Indexa los tests del repo GitHub de la org como `test_assets` (embeddings) |
| **CI** | `src/ci/` | Webhook CI (HMAC), GitHub App auth, CiIngestionService (atómica e idempotente por `run_uid`) |
| **Onboarding** | `src/onboarding/` | domain_summary + learning_path usando KnowledgeService |
| **Orgs** | `src/orgs/` | OrganizationRepository: create, join, list |
| **Integrations** | `src/jira/` | IntegrationsRepository: upsert/get Jira, GitHub y Xray configs (cifrado Fernet, `MNEMO_SECRET_KEY`) |
| **AI** | `src/ai/` | nl_query (ask), briefing, generate, judge (LLM-judge → `self_eval` del acta) |
| **LLM** | `src/llm/` | Providers intercambiables: factory, ollama, openai-compatible, anthropic, reasoning |
| **Infra** | `src/security.py`, `src/db/pool.py`, `src/sanitizer.py`, `src/demo/` | Auth JWT (JWKS/HS256), pool de conexiones pre-calentado en lifespan, redacción de secretos/PII, seed de demo |

## Principios de diseño

**Funciones puras** donde se pueda (parsers, fingerprint, match, centroid, verdict → testeables sin BD/LLM). **Dependencias inyectables y perezosas** (embedder, narrator, repo) para no cargar modelos en import y poder mockear. **LLM fuera del camino crítico**: la ingesta y el motor de reglas del triaje son deterministas (embeddings + SQL); los casos ambiguos (regla `R6`) pasan por un desempate LLM y quedan marcados `llm_assisted` — y un acta con cualquier veredicto asistido **nunca** es un `apto` rotundo. Todo lo LLM degrada con elegancia si el proveedor no responde.

## Flujo Autopilot (fuente de memoria)

```
POST /v2/ci/webhook (artefacto CI firmado; procesado en threadpool, fuera del event loop)
  → CiIngestionService → test_run + failures + defect_families   (idempotente por run_uid)
  → TriageService → triage_verdicts (R0–R6; ambiguos → desempate LLM)
  → CertificateService → certificado firmado Ed25519
  → GateService → commit status en GitHub
         │
         ▼  las correcciones humanas (re-etiquetado de familias) alimentan:
  triage_corrections → calibración del motor (el "foso")
```

La memoria (`qa_knowledge`) se puebla hoy **manualmente** (`POST /v2/knowledge`); la auto-población desde el triaje (defecto recurrente → lección) está en el roadmap.

## Flujo de ingesta manual

```
POST /v2/ingest/report (multipart: file, project, source, org_id)
  → IngestionService.ingest_report
      detect_source/parser(source) → FailureRecord[]
      por cada fallo: sanitize_text → fingerprint → embed
      run_uid = hash del archivo (re-subir el mismo reporte deduplica)
      → AssuranceRepository.ingest_run (una transacción):
          verifica membership (PermissionError si no)
          crea test_run
          por cada item: coseno → decide_match
              nuevo → crea defect_family (centroid=embedding, occ=1)
              conocido → update_centroid + occ+1 + last_seen
          inserta failure (con defect_family_id)
  ← {run_id, ingested, known, novel, deduplicated}
```

## Acta firmada y política de veredicto (§7.1)

- **Firma Ed25519** (`src/certify/signing.py`) sobre el **JSON canónico** determinista del acta; el `key_id` (SHA-256 truncado de la clave pública) viaja dentro y habilita rotación sin romper actas antiguas.
- **Verificación pública sin cuenta**: `GET /v2/certificates/pubkey` + `POST /v2/certificates/verify` (o la página `/verify`, u offline).
- **Política (§7.1, `src/certify/certificate.py`)**: `no-apto` si hay fallo real nuevo sin aprobación o veredictos pendientes de aprobación; `apto-con-reservas` si hay real/mantenimiento, la confianza de calibración es baja o **cualquier** veredicto fue asistido por LLM; `apto` solo cuando todo lo anterior es falso. `risk_score = min(100, 40·novel + 20·pendientes + 10·recurrentes + 2·flaky)`.

## Veredicto de aseguramiento

`GET /v2/assurance/run/{id}` → `get_run_assurance_data` → `build_verdict` (determinista: risk, top_families) → `narrator.summarize` (LLM opcional; si falla, `narrative=null`) → `AssuranceVerdictResponse`.

## Privacidad / eficiencia

- Embeddings **siempre locales** (CPU, sin GPU). LLM configurable: **Ollama local → coste de API 0 € y data-residency** (la promesa on-premise); en el deploy de demo, Gemini free tier con opt-in explícito (`ALLOW_EXTERNAL_LLM=true` — los datos de fallos van a un tercero).
- `sanitizer.py` redacta secretos/PII antes de persistir.
- La ingesta es barata (embeddings + SQL); los LLM solo se usan en el desempate de ambiguos y en paths opcionales (narrativa, briefing, ask, test-plan, onboarding, root-cause, automation).

## Despliegue

- **Backend:** `uvicorn asgi:app`. `asgi.py` monta únicamente el router `/v2`; no existe `api.py` en el árbol de producción.
- **Frontend:** build de Next (`npm run build`); el proxy `/api/v2/*` reenvía a `NEXT_PUBLIC_API_BASE_URL`.
- **BD:** Supabase. **Importante:** usar la cadena del **Session pooler** (IPv4); la conexión directa `db.<ref>.supabase.co` es IPv6-only y puede no enrutar. Ver `docs/technical/modelo-datos.md`.
- Guía completa: `docs/deploy/produccion.md`.
- **Roadmap:** appliance **air-gapped** (todo local, sin internet) para sectores regulados — el LLM local lo hace posible.
