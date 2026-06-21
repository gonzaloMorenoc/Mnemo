# Mnemo — Memoria de QA para consultoras

**Mnemo** es una plataforma **privada y on-premise** que convierte los fallos de los runs de test en **conocimiento reutilizable** (Defect DNA) y en **veredictos de aseguramiento** automáticos. Pensada para una consultora de QA multi-cliente: retiene el conocimiento que de otro modo se evapora con la rotación de personal.

> Evolución de *SmartErrorDebugger* (un "AI debugger" de pegar trazas). Se reposicionó porque el valor real no es depurar un error, sino **no perder el conocimiento de QA**. Depurar es una función, no el producto. Ver [`docs/adr/0001-pivote-a-mnemo.md`](docs/adr/0001-pivote-a-mnemo.md).

## Qué hace

- **Ingesta** de reportes **Allure** (JSON) / **JUnit** (XML) → extrae fallos, los **sanitiza** y les calcula una huella (**fingerprint**).
- **Defect DNA**: agrupa los fallos en **familias de defecto** y reconoce el mismo defecto **entre proyectos y en el tiempo** (linaje), aunque cambien líneas/UUIDs/timestamps.
- **Assurance Autopilot**: por cada run, un **veredicto** — conocidos vs nuevos, señal de riesgo, familias recurrentes y narrativa LLM (que degrada con elegancia si el LLM no está).
- **Privado por diseño**: LLM y embeddings **locales** (Ollama + HuggingFace). El dato del cliente **nunca sale** (con el proveedor LLM por defecto `ollama`; usar un proveedor comercial requiere `ALLOW_EXTERNAL_LLM=true` y envía datos a un tercero). Coste de API = 0 €.

## Stack

Python 3.13 · FastAPI · Postgres + pgvector (Supabase) · Supabase JWT · Ollama (DeepSeek-R1) · HuggingFace embeddings · Next.js + TanStack Query + shadcn/ui · pytest/vitest.

## Documentación

| Doc | Contenido |
|---|---|
| [`docs/functional/overview.md`](docs/functional/overview.md) | Visión de producto, propuesta de valor, personas, casos de uso, demo |
| [`docs/technical/arquitectura.md`](docs/technical/arquitectura.md) | Arquitectura, capas, componentes, flujo de datos, despliegue |
| [`docs/technical/modelo-datos.md`](docs/technical/modelo-datos.md) | Esquema (runs/failures/defect_families) y **aislamiento** (RLS vs filtros de membership) |
| [`docs/technical/api.md`](docs/technical/api.md) | Referencia de endpoints `/v2` |
| [`docs/adr/0001-pivote-a-mnemo.md`](docs/adr/0001-pivote-a-mnemo.md) | ADR del pivote (qué se reutiliza/poda) |
| [`doc/AUDITORIA_CONCURSO_MTP.md`](doc/AUDITORIA_CONCURSO_MTP.md) | Auditoría y encaje con el concurso MTP AI Innovation Award |

## Puesta en marcha (resumen)

1. **Modelos locales:** `ollama pull deepseek-r1:8b`.
2. **Dependencias:** `pip install -r requirements.txt`.
3. **BD (Supabase):** configurar `DATABASE_URL` (cadena del **Session pooler**, no la directa IPv6-only) + `SUPABASE_URL`/`SUPABASE_JWKS_URL` en `.env`; aplicar migraciones `db/migrations/001_*.sql` y `002_*.sql`.
4. **Backend:** `uvicorn api:app`.
5. **Frontend:** `cd frontend && npm install && npm run build` (proxy `/api/v2/*` → `NEXT_PUBLIC_API_BASE_URL`).
6. **Datos de demo (opcional):** `python scripts/seed_demo.py` (siembra proyectos con una familia compartida).

## Endpoints `/v2`

`POST /v2/ingest/report` · `GET /v2/defects` · `GET /v2/defects/{id}` · `GET /v2/assurance/run/{id}` · `GET/POST /v2/orgs` · `POST /v2/orgs/join` · `POST /v2/analyze` · `POST /v2/upload` · `GET /v2/health`. Detalle en [`docs/technical/api.md`](docs/technical/api.md).

## Tests

```bash
python3 -m pytest -m "not integration"   # unitarios (sin BD/LLM)
python3 -m pytest -m integration         # integración (requiere DATABASE_URL)
cd frontend && npm test                  # vitest
```

## Nota sobre el legacy

El camino RAG single-tenant original (`ui.py` Streamlit, `vector_store.py` Chroma, endpoints `/analyze`, `/sync`…) **coexiste** con el camino `/v2` de Mnemo hasta que sea sustituido por completo (ver ADR 0001).
