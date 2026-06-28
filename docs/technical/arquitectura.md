# Mnemo — Arquitectura técnica

## Visión: QA Continuity AI

Mnemo es una plataforma de **continuidad operativa de QA**: captura la memoria del equipo (patrones de defecto, conocimiento de dominio, decisiones pasadas) y la usa para acelerar el trabajo de QA del día a día. El lazo Autopilot (triaje → acción → certificado) es la **fuente principal de datos** que alimenta la memoria, no el centro del producto.

## Stack

- **Backend:** Python 3.13, FastAPI. LLM y embeddings **locales**: `qwen3:8b` vía **Ollama** (por defecto), con soporte para OpenAI y Anthropic mediante `LLM_PROVIDER`/`ALLOW_EXTERNAL_LLM`. Embeddings: `all-MiniLM-L6-v2` (384 dims) vía HuggingFace.
- **Datos:** **Postgres + pgvector** (Supabase). Auth: **Supabase JWT** (verificación por JWKS).
- **Frontend:** Next.js (App Router) + React + TypeScript + TanStack Query + shadcn/ui; auth Supabase.

## Capas

```
  Frontend Next.js
  (/app/assurance, /app/defects, /app/knowledge, /app/test-plan, /app/onboarding, /app/graph)
                       │  (proxy /api/v2/* → backend /v2/*)
                       ▼
   FastAPI  asgi.py ──include──►  src/api_v2.py  (router /v2, auth JWT, deps perezosas)
                       │
      ┌────────────────┼──────────────────────────────────────────────┐
      ▼                ▼                    ▼                          ▼
  Ingest+Triage    Knowledge+Graph      TestPlan+Xray         Automation+CI
  (src/defects/    (src/knowledge/      (src/testplan/        (src/automation/
   src/triage/      src/graph/)          src/xray/)            src/ci/)
   src/actions/
   src/certify/)
      │                │                    │                          │
  Postgres+pgvector   Postgres+pgvector   Ollama (LLM)           GitHub App
  Ollama (LLM, perezoso)  Ollama (LLM)   Xray API
```

## Módulos de capacidad

| Módulo | Ruta | Responsabilidad |
|--------|------|-----------------|
| **Ingest** | `src/ingest/` | Parsers de reportes (Allure/JUnit), modelos, fingerprint, embedder, ingestion_service |
| **Defects / Defect DNA** | `src/defects/` | AssuranceRepository, match, centroid, narrator, `src/assurance/` |
| **Triage** | `src/triage/` | TriageService: clasifica fallos en flaky/infra/maintenance/real/unknown |
| **Actions** | `src/actions/` | ActionService + ActionRepository: propone y materializa acciones (quarantine/ticket/self_heal) |
| **Certify** | `src/certify/` | CertificateService: genera y firma certificados de release assurance; GateService |
| **Knowledge** | `src/knowledge/` | QaKnowledgeRepository + KnowledgeService: memoria RAG de QA |
| **Graph** | `src/graph/` | GraphService: grafo de conocimiento (dominios → familias → ítems); detect_gaps |
| **TestPlan** | `src/testplan/` | Generación de planes de prueba desde HUs; `src/xray/`: exportación a Jira/Xray |
| **Automation** | `src/automation/` | Generación de tests Playwright (.spec.ts) desde casos |
| **CI** | `src/ci/` | Webhook CI, GitHub App auth, ingestion_service CI, webhook_auth |
| **Onboarding** | `src/onboarding/` | domain_summary + learning_path usando KnowledgeService |
| **Orgs** | `src/orgs/` | OrganizationRepository: create, join, list |
| **Integrations** | `src/jira/` | IntegrationsRepository: upsert/get Jira y GitHub configs (cifrado Fernet) |
| **AI** | `src/ai/` | nl_query (ask defects), briefing, LLM providers (factory, ollama, openai, anthropic) |

## Principios de diseño

**Funciones puras** donde se pueda (parsers, fingerprint, match, centroid, verdict → testeables sin BD/LLM). **Dependencias inyectables y perezosas** (embedder, narrator, repo) para no cargar modelos en import y poder mockear. **LLM fuera del camino crítico**: la ingesta y el triaje son deterministas (embeddings + SQL); el LLM se usa para narrativas/briefings/ask y degrada con elegancia si Ollama no responde.

## Flujo Autopilot (fuente de memoria)

```
POST /v2/ci/webhook (artefacto CI firmado)
  → CI ingestion_service → test_run + failures + defect_families
  → TriageService → triage_verdicts (flaky/infra/maintenance/real)
  → CertificateService → certificate (firmado)
  → GateService → commit status en GitHub
         │
         ▼  cada veredicto/corrección alimenta:
  qa_knowledge + triage_corrections → memoria del equipo
```

## Flujo de ingesta manual

```
POST /v2/ingest/report (multipart: file, project, source, org_id)
  → IngestionService.ingest_report
      parser(source) → FailureRecord[]
      por cada fallo: sanitize_text → fingerprint → embed
      → AssuranceRepository.ingest_run (una transacción):
          verifica membership (PermissionError si no)
          crea test_run
          por cada item: coseno → decide_match
              nuevo → crea defect_family (centroid=embedding, occ=1)
              conocido → update_centroid + occ+1 + last_seen
          inserta failure (con defect_family_id)
  ← {run_id, ingested, known, novel}
```

## Veredicto de aseguramiento

`GET /v2/assurance/run/{id}` → `get_run_assurance_data` → `build_verdict` (determinista: risk, top_families) → `narrator.summarize` (LLM opcional; si falla, `narrative=null`) → `AssuranceVerdictResponse`.

## Privacidad / eficiencia

- LLM y embeddings locales (`qwen3:8b` + `all-MiniLM-L6-v2`) → **coste de API 0 €** y data-residency.
- `sanitizer.py` redacta secretos/PII antes de persistir.
- La ingesta es barata (embeddings + SQL); los LLM solo se usan en paths opcionales (narrativa, briefing, ask, test-plan, onboarding).
- El proveedor LLM es configurable: `LLM_PROVIDER=ollama` (por defecto), `openai` o `anthropic` (requieren `ALLOW_EXTERNAL_LLM=true`).

## Despliegue

- **Backend:** `uvicorn asgi:app`. `asgi.py` monta únicamente el router `/v2`; no existe `api.py` en el árbol de producción.
- **Frontend:** build de Next (`npm run build`); el proxy `/api/v2/*` reenvía a `NEXT_PUBLIC_API_BASE_URL`.
- **BD:** Supabase. **Importante:** usar la cadena del **Session pooler** (IPv4); la conexión directa `db.<ref>.supabase.co` es IPv6-only y puede no enrutar. Ver `docs/technical/modelo-datos.md`.
- **Roadmap:** appliance **air-gapped** (todo local, sin internet) para sectores regulados — el LLM local lo hace posible.
