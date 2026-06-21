# Slice 2 — Conector de bugs de Jira → Defect DNA

**Fecha:** 2026-06-20
**Estado:** Diseño aprobado (pendiente de plan de implementación)

## Contexto

Mnemo agrupa los fallos de runs de test en familias de defecto (Defect DNA). Un **bug
de Jira es un defecto registrado a mano**: traerlo a las mismas familias unifica los
defectos manuales con los automáticos ("este bug PROJ-123 es la misma familia que estos
30 fallos de Selenium"), aprovechando el matching semántico por embedding.

El pipeline existente es `test_runs → failures → defect_families`, alimentado por
`AssuranceRepository.ingest_run(*, user_id, org_id, project, source, items)` donde cada
`IngestItem(rec: FailureRecord, fingerprint, embedding)`. `requirements.txt` ya incluye
`atlassian-python-api` (cliente oficial de Jira) y `requests`.

## Objetivo

Integrar los **issues de tipo Bug de Jira** en el Defect DNA por **dos vías**: subir un
**export** (CSV/JSON) y **traerlos en vivo** vía la API de Jira (JQL). Ambas convergen en
un mapeo común bug→`IngestItem` que reutiliza `ingest_run` con `source="jira"`.

## Alcance

**Incluido:**
- Modelo normalizado `JiraBug` + mapper a `IngestItem`.
- Parser de export de Jira (CSV y JSON de `/rest/api/3/search`).
- Cliente API en vivo (`atlassian-python-api`) con JQL y paginación.
- Credenciales por org cifradas (tabla `org_integrations`, Fernet).
- Servicio de ingesta de Jira con dedup por `external_ref`.
- Endpoints `/v2/integrations/jira` (config) y `/v2/ingest/jira/{file,pull}`.
- Migración 005 (CHECK `source`, columnas `external_ref`/`external_url`, tabla `org_integrations`).
- Frontend: página de integraciones (config + importar).
- Validación SSRF de la `base_url`.
- Tests unitarios (TDD) + integración.

**Fuera de alcance (slices posteriores):**
- Confluence / KB de contexto.
- Otros proveedores (GitHub Issues, Azure Boards, etc.).
- Importación incremental programada (webhooks/cron). Esta versión importa bajo demanda.
- Sincronización bidireccional (Mnemo no escribe en Jira).

## Arquitectura

```
                       ┌── parse_jira_export(bytes) ──┐
  archivo (CSV/JSON) ──┤                              │
                       │                              ▼
  API (JQL) ───────────┴── JiraApiClient.fetch_bugs ──► List[JiraBug]
                                                        │
                                                        ▼
                                      map_bug_to_item (fingerprint+embed)
                                                        │
                                                        ▼
                       JiraIngestionService (dedup external_ref) ──► ingest_run(source="jira")
```

Una **interfaz de fuente** común: ambas vías producen `List[JiraBug]`; el resto del
camino es idéntico.

## Componentes

### Modelo normalizado (`src/jira/models.py`)

```python
@dataclass
class JiraBug:
    key: str            # PROJ-123 (issue key, único por org → external_ref)
    summary: str
    description: str     # texto plano (ADF aplanado si viene de la API v3)
    issue_type: str      # "Bug", ...
    status: str          # "Open", "Done", ...
    url: str             # enlace al issue (external_url)
```

Helper `adf_to_text(value)`: si `description` es un dict ADF (API v3), extrae el texto
plano recorriendo los nodos `text`; si es str, la devuelve tal cual; si es None, "".

### Mapper (`src/jira/mapper.py`)

`bug_to_record(bug, *, project) -> FailureRecord`: `test_name=bug.key`,
`error_type=bug.issue_type`, `message=bug.summary`, `trace=bug.description or None`,
`project=project`, `source="jira"`. El fingerprint se calcula sobre el record (igual que
los fallos); el embedding sobre `f"{bug.summary} {bug.description}"`. El issue key
(`bug.key`) y `bug.url` se propagan como `external_ref`/`external_url` (ver repositorio).

### Parser de export (`src/jira/export.py`)

`parse_jira_export(data: bytes) -> List[JiraBug]`:
- **JSON** (resultado de `/rest/api/3/search`): objeto con `issues[]`, cada uno
  `{key, fields:{summary, description, issuetype:{name}, status:{name}}}`. Filtra a
  `issuetype.name == "Bug"` (case-insensitive).
- **CSV** (export estándar de Jira, módulo `csv` de stdlib): columnas `Issue key`,
  `Summary`, `Description`, `Issue Type`, `Status`. Filtra filas con `Issue Type == "Bug"`.
- Distingue JSON vs CSV por el primer byte no-espacio (`{`/`[` → JSON, si no → CSV).
- `url` se deja vacío en el export (no siempre disponible); el repositorio tolera `external_url` nulo.
- Lanza `ValueError` ante contenido inválido.

### Cliente API (`src/jira/client.py`)

`JiraApiClient(base_url, email, token)` envuelve `atlassian.Jira`. Método
`fetch_bugs(jql: str, *, page_size=50, max_issues=1000) -> List[JiraBug]`:
- Ejecuta `jql` paginando (`start`/`limit`) hasta agotar `total` o llegar a `max_issues`
  (cota dura para no traer importaciones enormes; se registra si se trunca).
- Campos pedidos: `summary,description,issuetype,status`.
- Mapea cada issue a `JiraBug` (con `adf_to_text` sobre la description).
- Errores de red/credenciales se propagan como `JiraApiError` (envuelve la excepción de
  la librería) para que el endpoint los traduzca a 502.

### Validación SSRF (`src/jira/safe_url.py`)

`validate_base_url(url: str) -> str`: acepta solo `https://`; resuelve el host y rechaza
loopback, privadas (RFC1918), link-local y la IP de metadatos cloud (169.254.169.254);
devuelve la URL normalizada o lanza `ValueError`. Se aplica al **guardar** la config y
antes de **cada** llamada saliente.

### Credenciales cifradas (`src/jira/crypto.py` + repositorio)

- `cryptography` (Fernet) — **nueva dependencia** en `requirements.txt`.
- `encrypt_token(plain) / decrypt_token(enc)` usan la clave `MNEMO_SECRET_KEY` (env);
  si falta, el arranque del servicio de integraciones falla con mensaje claro.
- Tabla `org_integrations(org_id, provider, base_url, email, api_token_enc, jql, ...)`.
- `IntegrationsRepository`: `upsert_jira_config` (cifra el token), `get_jira_config`
  (devuelve config **sin** token, para lectura), `get_jira_credentials` (descifra, uso
  interno solo en el pull). Acceso por membership (capa app, como el resto — el pooler
  bypassa RLS).

### Servicio (`src/jira/ingestion_service.py`)

`JiraIngestionService.ingest_bugs(*, user_id, org_id, project, bugs) -> dict`:
- Mapea bugs → `IngestItem` (mapper + fingerprint + embedder).
- **Dedup**: omite bugs cuyo `external_ref` (issue key) ya exista en `failures` de la org
  (consulta previa); registra cuántos se omitieron.
- Llama `repo.ingest_run(..., source="jira", items=...)`, donde cada `IngestItem` ya lleva
  `external_ref`/`external_url` (ver Repositorio).
- `ingest_from_pull(*, user_id, org_id, project)`: carga credenciales, valida URL,
  `JiraApiClient.fetch_bugs`, luego `ingest_bugs`.

### Repositorio (extensión de `AssuranceRepository`)

`ingest_run` gana un parámetro opcional paralelo a `items` para `external_ref`/
`external_url` por item (lista alineada con `items`, o un campo nuevo en `IngestItem`).
**Decisión:** añadir `external_ref: Optional[str]` y `external_url: Optional[str]` a
`IngestItem` (default None) y persistirlos en `failures` — los reportes de test los dejan
en None, los bugs los rellenan. Esto evita cambiar la firma de `ingest_run`.

### Endpoints (`src/api_v2.py`)

- `POST /v2/integrations/jira` (body: base_url, email, token, jql?) → guarda/actualiza;
  valida SSRF; **no** devuelve el token. 200 `{configured: true}`.
- `GET /v2/integrations/jira?org_id=` → `{configured, base_url, email, jql}` (sin token).
- `POST /v2/ingest/jira/file` (multipart: file, project, org_id) → parse export + ingest.
- `POST /v2/ingest/jira/pull` (body: project, org_id) → pull vía API + ingest.
- Mapeo de errores: `PermissionError`→403, `ValueError`/`OSError`→400, `JiraApiError`→502,
  `psycopg.Error`→502.

### Migración (`db/migrations/005_jira_integration.sql`)

```sql
alter table public.test_runs drop constraint test_runs_source_check;
alter table public.test_runs add constraint test_runs_source_check
    check (source in ('allure','junit','testng','cucumber','playwright','cypress','robot','jira'));

alter table public.failures add column if not exists external_ref text;
alter table public.failures add column if not exists external_url text;

create table if not exists public.org_integrations (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    provider text not null check (provider in ('jira')),
    base_url text not null,
    email text not null,
    api_token_enc text not null,
    jql text not null default 'issuetype = Bug',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, provider)
);
create index if not exists idx_org_integrations_org on public.org_integrations (org_id);
```

### Frontend (`frontend/src/app/app/integrations/page.tsx` + nav + cliente API)

Página "Integraciones": formulario de config Jira (base URL, email, API token, JQL) que
hace `POST /v2/integrations/jira`; un botón "Importar bugs ahora" → `POST /v2/ingest/jira/pull`;
y subir un export → `POST /v2/ingest/jira/file`. Muestra `ingested/known/novel/omitidos`.
Reutiliza el patrón existente (TanStack Query, queryKey `["organizations", accessToken]`,
estados de carga/error). Tipos y funciones cliente en `src/lib/api/{types,endpoints}.ts`.

## Modelo de datos

Reutiliza `failures`/`defect_families` (enfoque A). Cambios: `source` admite `'jira'`;
`failures` gana `external_ref` (issue key) y `external_url` (link). Un import de Jira es
un `test_run` con `source='jira'` y `project` = el indicado por el usuario. Los bugs se
agrupan con los fallos automáticos por **similitud semántica** (cosine del embedding); el
fingerprint exacto rara vez coincidirá entre texto natural y stacktrace, y eso es esperado.

## Manejo de errores

| Situación | Resultado |
|---|---|
| `base_url` no https o apunta a IP interna/metadata | `ValueError` → **400** (SSRF rechazado) |
| Export inválido (CSV/JSON corrupto) | `ValueError` → **400** |
| Pull sin integración configurada | `ValueError` → **400** "configura Jira primero" |
| Credenciales inválidas / Jira inalcanzable | `JiraApiError` → **502** (sin filtrar el token) |
| Usuario no miembro de la org | `PermissionError` → **403** |
| Re-importar bugs ya presentes | omitidos por dedup (no duplica), contados en la respuesta |

## Seguridad

- **Token cifrado en reposo** (Fernet, `MNEMO_SECRET_KEY`); nunca se devuelve en lecturas
  ni se escribe en logs.
- **SSRF**: `validate_base_url` (solo https, sin loopback/privadas/link-local/metadata) al
  guardar y antes de cada pull.
- **Aislamiento por membership** en todas las consultas (el pooler bypassa RLS).
- El JQL es controlado por el usuario; se pasa tal cual a la API de Jira (no se concatena
  en SQL local), así que no hay inyección en Mnemo.

## Testing (TDD)

- `parse_jira_export`: fixtures JSON (search) y CSV reales; filtra no-Bug; inválido→ValueError.
- `adf_to_text`: ADF anidado → texto; str→str; None→"".
- `JiraApiClient.fetch_bugs`: HTTP mockeado (monkeypatch sobre `atlassian.Jira.jql`),
  verifica paginación, campos y `max_issues`; error de la librería → `JiraApiError`.
- `validate_base_url`: acepta https público; rechaza http, loopback, 10.x, 169.254.169.254.
- `crypto`: round-trip encrypt/decrypt; clave ausente → error claro.
- Mapper + dedup: bug→record correcto; re-import omite duplicados.
- `JiraIngestionService` con repo y embedder mock.
- Endpoints con dependencias mock (incl. que GET no devuelve el token).
- **Integración**: `upsert_jira_config` + `get_jira_config` (sin token) + ingesta de un
  export → familia con `external_ref` poblado, contra Supabase.

## Decisiones de diseño

- **Enfoque A** (bug como fallo sintético) — reutiliza matching/familias/linaje/veredicto;
  el valor de unificar manual+automático sale gratis.
- **`atlassian-python-api`** para el cliente API (ya es dependencia) en vez de REST manual.
- **Fernet** para el token (dependencia nueva `cryptography`); alternativa pgcrypto
  descartada por mantener el cifrado en la capa de app y testeable sin BD.
- **Dedup por `external_ref`** para que re-importar (archivo o pull) sea idempotente.
- `max_issues` como cota dura del pull para evitar importaciones gigantes accidentales.
