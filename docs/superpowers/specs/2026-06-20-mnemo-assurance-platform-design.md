# Spec — Mnemo: plataforma de memoria de QA (slice vertical para el concurso)

**Fecha:** 2026-06-20
**Rama:** `feat/mnemo-assurance` (desde `main`)
**Nombre de producto:** **Mnemo** (de *Mnemosyne*, la memoria)
**Contexto:** evolución de SmartErrorDebugger. Decisión estratégica y mapa de reutilización en `doc/AUDITORIA_CONCURSO_MTP.md` y en el análisis de posicionamiento de esta misma sesión. Plazo del MTP AI Innovation Award: 30-oct-2026.

---

## 1. Objetivo y no-objetivos

**Objetivo (este spec):** entregar un **slice vertical end-to-end** demo-able que cuente la historia completa de Mnemo:
**ingesta de reportes de test (Allure/JUnit) → fingerprint + matching → veredicto de aseguramiento del run → dashboard de "Defect DNA" (familias de defecto y linaje entre proyectos)**, sembrado con datos de 2-3 proyectos de ejemplo.

**No-objetivos (roadmap, fuera de este slice):** webhook de CI en vivo, conectores adicionales (Jira/GitHub), packaging air-gapped como appliance, generación de tests, analítica de portfolio avanzada. El **air-gapped** se documenta como argumento de viabilidad; no se construye aún.

**Posicionamiento:** Mnemo es la **memoria de QA** de una consultora: privada (LLM 100% local, on-prem), federada por proyecto/cliente, que convierte fallos de test dispersos en conocimiento reutilizable y veredictos de aseguramiento. "Depurar" es una función, no el producto.

## 2. Producto (funcional)

### Personas
- **QA / Test Automation Engineer**: sube/recibe resultados de un run; quiere saber qué es nuevo y qué ya se conoce (y su fix).
- **Delivery / QA Manager**: quiere ver salud de calidad por proyecto y defectos recurrentes (Defect DNA).

### Casos de uso del slice
1. **Ingesta de un run**: subir un reporte Allure/JUnit de un proyecto → Mnemo extrae los fallos.
2. **Veredicto de aseguramiento**: por cada run, Mnemo dice cuántos fallos son **conocidos** (con su familia/fix) vs **novedosos**, y da una **señal de riesgo** + narrativa. *Heurística del slice:* `atención` si hay fallos novedosos o reaparece una familia marcada como `resolved`; si no, `ok`.
3. **Defect DNA**: dashboard de **familias de defecto** con ocurrencias en el tiempo y **linaje entre proyectos** (la misma familia apareciendo en varios proyectos de la org).

### Guion de demo (2-3 min)
Org "MTP" con 3 proyectos (clientes). Se ingieren reportes; un *timeout* aparece en 2 proyectos → el dashboard muestra esa familia con linaje cross-proyecto y su fix conocido; un run nuevo trae un fallo novedoso → el veredicto lo marca como nuevo.

### Decisión de alcance sobre "cross-proyecto" vs "cross-cliente"
En el slice, **una org (la consultora) con varios `project`** (clientes). Las familias de defecto son **org-scoped** y abarcan proyectos → muestra "el mismo defecto en varios proyectos" **sin** complejidad de RLS cross-tenant. El federado **cross-cliente** (scope `global` sanitizado entre orgs) queda como roadmap.

## 3. Arquitectura (técnica) — evolución sobre la plataforma existente

Se reutiliza el núcleo ya construido (FastAPI `/v2`, Postgres+pgvector+RLS, auth Supabase, embeddings HF locales, LLM Ollama, `structured_analyzer`, frontend Next.js). Se añaden módulos nuevos y se poda el legacy.

```
Reporte Allure/JUnit
   │  POST /v2/ingest/report (multipart: file, project, source)
   ▼
src/ingest/{allure,junit}.py  → FailureRecord[]
   ▼
src/sanitizer.py (endurecido)  → redacción de secretos/PII
   ▼
src/defects/fingerprint.py     → signature normalizada + embedding (HF local)
   ▼
src/defects/matcher.py         → empareja con defect_families (fingerprint exacto | coseno > umbral)
   ▼   (si no hay match) src/defects/clustering.py → crea familia nueva
   ▼
persistencia: test_runs / failures / defect_families  (Postgres + pgvector, RLS por org)
   ▼
src/assurance/report.py        → veredicto del run (resumen LLM async, vía structured_analyzer)
   ▼
Frontend (Next.js): páginas "Assurance" y "Defect DNA"
```

**Principio:** el LLM va **fuera del camino crítico** de ingesta (async/on-demand) → eficiencia. La ingesta + matching usa solo embeddings + SQL (barato).

## 4. Modelo de datos (migración nueva `db/migrations/002_assurance.sql`)

Sobre el esquema actual (reutiliza `organizations`, `memberships`, patrón RLS). Embeddings `vector(384)` (coherente con `all-MiniLM-L6-v2`).

| Tabla | Campos clave | Notas |
|---|---|---|
| `test_runs` | id, org_id, project, source(`allure`/`junit`), ci_ref?, summary jsonb?, created_at | RLS: miembro de la org |
| `defect_families` | id, scope(`org`/`global`), org_id?, signature, title, root_cause?, status(`open`/`resolved`), first_seen, last_seen, occurrence_count, centroid vector(384)?, created_at | CHECK: `org`→org_id not null; `global`→org_id null. RLS |
| `failures` | id, run_id, org_id, test_name, error_type?, message, trace?, fingerprint, embedding vector(384), sanitized bool, defect_family_id?, created_at | RLS por org. Índices: ivfflat(embedding), fingerprint, defect_family_id |

- **Linaje** = `failures` agrupados por `defect_family_id` a través de `test_runs.project` y tiempo.
- `ALTER TABLE ... FORCE ROW LEVEL SECURITY` en las 3 tablas (cierra el hueco detectado en la auditoría).
- **Nota de alcance:** en el slice el matching usa **solo scope `org`**; el scope `global` queda en el esquema para el roadmap federado cross-cliente, sin ejercitarse todavía.

## 5. Componentes nuevos (interfaces claras, archivos pequeños)

| Módulo | Responsabilidad | Interfaz |
|---|---|---|
| `src/ingest/allure.py` | Parsear `*-result.json` Allure → records | `parse_allure(data: bytes) -> list[FailureRecord]` |
| `src/ingest/junit.py` | Parsear JUnit XML → records | `parse_junit(data: bytes) -> list[FailureRecord]` |
| `src/defects/fingerprint.py` | Signature normalizada (sin líneas/UUIDs/timestamps/paths) + embedding | `fingerprint(rec) -> str`, `embed(text) -> vector` |
| `src/defects/matcher.py` | Empareja un fallo con familia existente (scope org) | `match(cur, *, org_id, fingerprint, embedding) -> family_id | None` |
| `src/defects/clustering.py` | Crear/actualizar familia (centroide running-mean, contadores) | `assign_or_create(...) -> family_id` |
| `src/assurance/report.py` | Veredicto del run (conteos known/novel, top familias, narrativa LLM async) | `build_verdict(run_id) -> dict` |
| `src/api_v2.py` (extender) | Endpoints nuevos | ver §6 |

`FailureRecord` (dataclass): `test_name, error_type, message, trace, project, source`.

## 6. Endpoints nuevos (`/v2`, con `Depends(get_current_user)`)

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| POST | `/v2/ingest/report` | multipart: file + `project`, `source` | `{run_id, ingested, known, novel}` |
| GET | `/v2/assurance/run/{id}` | — | veredicto (known/novel, familias, narrativa, señal de riesgo) |
| GET | `/v2/defects` | query: `scope?`, `project?` | lista de familias (title, occurrence_count, last_seen, projects[]) |
| GET | `/v2/defects/{id}` | — | familia + linaje (failures por run/project, en el tiempo) |

Errores: auth 401, multitenant no configurado 503, validación 422, datos malos 400, DB 502 (mismo patrón que `/v2` actual).

## 7. Frontend (Next.js, reusando shell/auth/componentes)

- `/app/assurance`: subir reporte → ver veredicto del run (badges known/novel, narrativa, lista de fallos con su familia).
- `/app/defects`: dashboard Defect DNA — tabla de familias (ocurrencias, último visto, proyectos) + detalle con linaje (timeline / por proyecto).

## 8. Privacidad / sanitización

Endurecer `src/sanitizer.py` para cubrir los secretos comunes que hoy filtra (JWT, claves cloud, tokens `ghp_`/`xoxb-`, tarjetas, claves PEM) antes de persistir `message`/`trace`. Tests de no-fuga. (Es el argumento de "compartir conocimiento con confianza".)

## 9. Poda (deuda que estorba al relato)

Retirar `ui.py` (Streamlit), `app_legacy.py`, `src/vector_store.py` (Chroma single-tenant superado). Conservar `loader.py` como base de parsers. Actualizar `docker-compose.yml` para levantar API + frontend + Postgres/pgvector (+ Ollama), no la UI legacy.

## 10. Testing (TDD)

- Parsers: fixtures Allure/JUnit → records normalizados (casos: fallo, skip, passed ignorado, campos ausentes).
- `fingerprint`: determinismo (mismo error con líneas/UUIDs distintos → misma signature).
- `matcher`/`clustering`: similar→misma familia, distinto→familia nueva, centroide se actualiza.
- `assurance/report`: con LLM mockeado, conteos known/novel correctos.
- Endpoints: con repo/auth/LLM mockeados (patrón `tests/test_api_v2.py`).
- **RLS**: test de aislamiento — la org A no ve runs/failures/familias de la org B.

## 11. Documentación (entregable de primer nivel: estado actual + visión objetivo)

```
docs/
├── functional/
│   ├── overview.md          # qué es Mnemo, visión de aseguramiento, propuesta de valor
│   ├── personas-y-casos.md  # QA engineer / delivery manager + casos de uso
│   └── demo-walkthrough.md  # guion de la demo del concurso
├── technical/
│   ├── arquitectura.md      # diagrama, evolución desde SmartErrorDebugger, qué se reusa/poda
│   ├── modelo-datos.md      # ERD: test_runs/failures/defect_families + RLS
│   ├── api.md               # referencia de endpoints /v2
│   ├── ingesta.md           # formatos Allure/JUnit soportados
│   ├── privacidad-rls.md    # modelo multitenant, RLS, sanitización
│   └── despliegue.md        # docker-compose + nota air-gapped
└── adr/0001-pivote-a-mnemo.md  # por qué el giro, qué se reutiliza, qué se poda
```
README reposicionado a Mnemo. Cubre **lo que ya existe** (post-`/v2`) y **a dónde evoluciona**.

## 12. Criterios de aceptación

- [ ] `POST /v2/ingest/report` con un Allure de ejemplo crea `test_run` + `failures` + asigna/crea `defect_families`; devuelve conteos known/novel.
- [ ] Un mismo error (con líneas/UUIDs distintos) en dos proyectos cae en la **misma** familia → linaje cross-proyecto visible en `/v2/defects/{id}`.
- [ ] `GET /v2/assurance/run/{id}` devuelve veredicto con narrativa (LLM mockeado en tests).
- [ ] Dashboard "Defect DNA" muestra familias + linaje con datos sembrados (2-3 proyectos).
- [ ] Suite TDD verde (parsers, fingerprint, matcher, endpoints, RLS) sin depender de Supabase/Ollama (mocks).
- [ ] Documentación `docs/functional` + `docs/technical` completa; README reposicionado.
- [ ] Legacy podado; `docker-compose up` levanta el stack real.

## 13. Datos de demo (seed)

Script `scripts/seed_demo.py` (o fixtures): 1 org "MTP", 3 proyectos, con reportes Allure/JUnit que incluyen **una familia compartida** (p.ej. *timeout*) en 2 proyectos + fallos únicos, para que el linaje y el veredicto se vean reales.
