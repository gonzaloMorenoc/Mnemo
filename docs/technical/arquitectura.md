# Mnemo — Arquitectura técnica

## Stack

- **Backend:** Python 3.13, FastAPI. LLM y embeddings **locales**: DeepSeek-R1 vía **Ollama**, embeddings `all-MiniLM-L6-v2` (384 dims) vía HuggingFace.
- **Datos:** **Postgres + pgvector** (Supabase). Auth: **Supabase JWT** (verificación por JWKS).
- **Frontend:** Next.js (App Router) + React + TypeScript + TanStack Query + shadcn/ui; auth Supabase.

## Capas

```
                 Frontend Next.js  (/app/assurance, /app/defects)
                        │  (proxy /api/v2/* → backend /v2/*)
                        ▼
   FastAPI  api.py ──include──►  src/api_v2.py  (router /v2, auth JWT, deps perezosas)
                        │
        ┌───────────────┼────────────────────────────┐
        ▼               ▼                              ▼
  IngestionService   AssuranceRepository        verdict/narrator
  (src/defects/      (src/defects/              (src/assurance/)
   ingestion_service) repository.py)
        │               │                              │
   parsers+fingerprint  Postgres+pgvector         Ollama (LLM, perezoso)
   +sanitizer+embedder  (RLS + filtros membership)
```

## Componentes nuevos (Mnemo)

| Módulo | Responsabilidad |
|---|---|
| `src/ingest/models.py` | `FailureRecord` + `parse_error_type` |
| `src/ingest/allure.py` / `junit.py` | parsers de reportes → `FailureRecord[]` (lanzan `ValueError` en input malformado) |
| `src/defects/fingerprint.py` | firma sha1 determinista (normaliza líneas/UUIDs/hex/paths/números) |
| `src/defects/match.py` | `decide_match` puro: firma exacta → coseno ≥ umbral → familia nueva |
| `src/defects/centroid.py` | `update_centroid` media móvil incremental |
| `src/defects/embedder.py` | `Embedder` (Protocol) + `LocalEmbedder` (HF perezoso) |
| `src/defects/repository.py` | `AssuranceRepository`: `ingest_run`, `list_defects`, `get_lineage`, `get_run_assurance_data` |
| `src/defects/ingestion_service.py` | orquesta parse→sanitize→fingerprint→embed→`ingest_run` |
| `src/assurance/verdict.py` | `build_verdict` puro (known/novel, riesgo, familias top) |
| `src/assurance/narrator.py` | `Narrator` (Protocol) + `LocalNarrator` (Ollama perezoso) |
| `src/api_v2.py` | endpoints `/v2/ingest/report`, `/v2/defects`, `/v2/defects/{id}`, `/v2/assurance/run/{id}` |

Principios de diseño: **funciones puras** donde se pueda (parsers, fingerprint, match, centroid, verdict → testeables sin BD/LLM); **dependencias inyectables y perezosas** (embedder, narrator, repo) para no cargar modelos en import y poder mockear; **LLM fuera del camino crítico** (la ingesta usa solo embeddings + SQL; la narrativa va detrás y degrada con elegancia).

## Flujo de ingesta de un run

```
POST /v2/ingest/report (multipart: file, project, source, org_id)
  → IngestionService.ingest_report
      parser(source) → FailureRecord[]
      por cada fallo: sanitize_text(message/trace) → fingerprint → embed
      → AssuranceRepository.ingest_run (una transacción):
          verifica membership (PermissionError si no)
          crea test_run
          por cada item: candidatos por coseno → decide_match
              nuevo → crea defect_family (centroid=embedding, occ=1)
              conocido → update_centroid + occ+1 + last_seen (SELECT ... FOR UPDATE)
          inserta failure (con defect_family_id)
          guarda summary {ingested, known, novel}
  ← {run_id, ingested, known, novel}
```

## Veredicto

`GET /v2/assurance/run/{id}` → `get_run_assurance_data` (run + familias del run con `run_count`/`occurrence_count`) → `build_verdict` (determinista) → `narrator.summarize` (LLM; si falla, `narrative=null`) → `AssuranceVerdictResponse`.

## Privacidad / eficiencia

- LLM y embeddings locales → **coste de API 0 €** y data-residency (el log del cliente no sale).
- `sanitizer.py` redacta secretos/PII (email, IPv4, claves, etc.) antes de persistir; clave para el scope `global`.
- La ingesta es barata (embeddings + SQL); el LLM solo se usa para la narrativa del veredicto, perezoso y opcional.

## Coexistencia con el legacy (deuda conocida)

`api.py` aún expone el camino RAG **single-tenant** original (`/analyze`, `/sync`, `/history`, `/stats`, `/evaluate`) sobre `vector_store.py` (Chroma) + `BugAnalyzer`. Convive con el router `/v2` de Mnemo. La poda completa requiere refactorizar `api.py` y se deja para un incremento posterior; `app_legacy.py` (código muerto) sí se retira.

## Despliegue

- Backend: `uvicorn api:app` (necesita Ollama con `deepseek-r1:8b` para la narrativa).
- Frontend: build de Next (`npm run build`); el proxy `/api/v2/*` reenvía a `NEXT_PUBLIC_API_BASE_URL`.
- BD: Supabase. **Importante:** usar la cadena del **Session pooler** (IPv4); la conexión directa `db.<ref>.supabase.co` es IPv6-only y puede no enrutar. Ver `docs/technical/modelo-datos.md`.
- Roadmap: appliance **air-gapped** (todo local, sin internet) para sectores regulados — el LLM local lo hace posible.
