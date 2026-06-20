# Slice 1 — Más formatos de reporte + auto-detección híbrida

**Fecha:** 2026-06-20
**Estado:** Diseño aprobado (pendiente de plan de implementación)

## Contexto

Mnemo ingiere fallos de runs de test y los agrupa en familias de defecto (Defect DNA).
Hoy solo soporta dos formatos de reporte: **Allure** (JSON) y **JUnit** (XML). Cada
formato es un parser puro `parse_X(data: bytes, *, project: str) -> List[FailureRecord]`
registrado en `IngestionService._PARSERS`, y el valor `source` se valida también en la
BD (`test_runs.source CHECK (source in ('allure','junit'))`). El frontend de Assurance
expone un `<select>` con esos dos formatos y envía `source` al endpoint
`POST /v2/ingest/report`.

Ampliar el abanico de formatos soportados aumenta directamente cuántas herramientas de
QA pueden alimentar Mnemo, sin tocar el matching ni el veredicto.

## Objetivo

Añadir **cinco** parsers nuevos —TestNG, Cucumber, Playwright, Cypress (Mochawesome) y
Robot Framework— y una capa de **auto-detección de formato** por contenido, con la
opción de forzar el formato manualmente (enfoque híbrido). Total: 7 formatos.

## Alcance

**Incluido:**
- 5 parsers nuevos siguiendo el patrón existente.
- Un detector de formato por contenido (`detect_source`).
- Migración que amplía el `CHECK` de `test_runs.source` a los 7 valores.
- Wiring del endpoint para aceptar `source="auto"`.
- Frontend: `<select>` con "Auto-detectar" (default) + los 7 formatos.
- Tests unitarios (TDD) con fixtures reales por formato + tests del detector.

**Fuera de alcance (Slice 2, spec aparte):**
- Conectores a fuentes externas (Jira/Confluence), pull vía API, auth.
- Cambios en matching, fingerprint, embeddings, veredicto o aislamiento.
- Cambios en el modelo `FailureRecord`.

## Arquitectura

Se conserva el patrón actual. Se añade una capa de **detección** delante del registro
de parsers; el resto de la tubería (sanitizar → fingerprint → embed → `ingest_run`) no
cambia.

```
upload → POST /v2/ingest/report (source = "auto" | <formato>)
            │
            ▼
   IngestionService.ingest_report
            │  source == "auto"?  ── sí ──▶ detect_source(data) ──▶ source | None(→400)
            │                                                          │
            ▼                                                          ▼
   _PARSERS[source](data, project) ──▶ [FailureRecord]  (resto del flujo sin cambios)
```

## Componentes

### Parsers nuevos (`src/ingest/`)

Cada parser es un módulo propio, función pura, devuelve **solo los fallos**, reutiliza
`parse_error_type` de `models.py`, y lanza `ValueError` ante contenido inválido.

| Módulo | `source` | Formato | Detección de fallo | Mapeo a `FailureRecord` |
|---|---|---|---|---|
| `testng.py` | `testng` | XML root `<testng-results>` | `<test-method status="FAIL">` | `test_name`=`class@name`.`method@name`; `error_type`=`<exception class>`; `message`=`<exception><message>`; `trace`=`<full-stacktrace>` |
| `cucumber.py` | `cucumber` | JSON: lista de features | `step.result.status == "failed"` | `test_name`=`feature.name / scenario.name`; `message`=`step.result.error_message`; `error_type`=`parse_error_type(message)`; `trace`=`error_message` |
| `playwright.py` | `playwright` | JSON reporter nativo | `result.status in {failed,timedOut,interrupted}` | `test_name`=`spec.title` (+ proyecto si está); `message`=`error.message` (ANSI eliminado); `trace`=`error.stack`; `error_type`=`parse_error_type` |
| `cypress.py` | `cypress` | JSON Mochawesome | `test.state == "failed"` o `test.err` no vacío | `test_name`=`test.fullTitle`; `message`=`err.message`; `trace`=`err.estack`; `error_type`=`parse_error_type` |
| `robot.py` | `robot` | XML root `<robot>` (`output.xml`) | `<test>` con `<status status="FAIL">` | `test_name`=`test@name`; `message`=texto del `<status>` o último `<msg level="FAIL">`; `trace`=concatenación de msgs FAIL; `error_type`=`parse_error_type` |

Notas:
- **Mochawesome** anida `results[].suites[]` de forma recursiva; el parser recorre el
  árbol de suites en profundidad recogiendo `tests`.
- **Playwright** anida `suites[].specs[].tests[].results[]`; recorrido recursivo de
  `suites`.
- Limpieza de **secuencias ANSI** (`\x1b[...m`) en mensajes de Playwright/Cypress antes
  de mapear, para que el fingerprint sea estable.

### Detector (`src/ingest/detect.py`)

`detect_source(data: bytes, filename: str | None = None) -> str | None`

Inspecciona el **contenido** (no la extensión, que es ambigua). El orden de las reglas
resuelve solapamientos:

1. **Intenta XML** (`ET.fromstring`). Por nombre local del root tag:
   - `testng-results` → `testng`
   - `robot` → `robot`
   - `testsuite` / `testsuites` → `junit`
   - otro → `None`
2. **Intenta JSON** (`json.loads`):
   - dict con `suites` **y** `stats` → `playwright`
   - dict con `results` **y** `stats` → `cypress` (Mochawesome)
   - lista cuyo primer item tiene `elements` (y `keyword`) → `cucumber`
   - lista/objeto cuyo primer item tiene `statusDetails`, o `status` junto con `uuid`/`fullName` → `allure`
   - otro → `None`
3. Ni XML ni JSON válido → `None`.

El parámetro `filename` se admite como pista futura, pero la decisión es por contenido.
Maneja el nombre local cuando el root trae namespace (`{ns}tag`).

### Migración (`db/migrations/004_more_sources.sql`)

```sql
alter table public.test_runs drop constraint test_runs_source_check;
alter table public.test_runs add constraint test_runs_source_check
    check (source in ('allure','junit','testng','cucumber','playwright','cypress','robot'));
```

(El constraint actual se llama `test_runs_source_check`, verificado en la BD.)

### API (`src/api_v2.py`)

- `ingest_report_v2`: el formulario ya envía `source`. Si falta o llega vacío, se usa
  `"auto"`.
- El mapeo de errores existente se mantiene: `ValueError` → **400**. El detector
  devolviendo `None` produce un `ValueError("no se reconoció el formato; selecciónalo
  manualmente")` desde `IngestionService`.

### Registro y servicio (`src/defects/ingestion_service.py`)

- `_PARSERS` añade las 5 entradas nuevas.
- `ingest_report`: si `source == "auto"`, llama a `detect_source`; si devuelve `None`,
  lanza `ValueError` con mensaje claro. Si `source` es explícito y no está en `_PARSERS`,
  lanza `ValueError(f"unsupported source: {source}")` (comportamiento actual).

### Frontend (`frontend/src/app/app/assurance/page.tsx`)

- El `<select>` de "Formato" pasa a: **Auto-detectar** (`value="auto"`, opción por
  defecto) seguido de las 7 opciones explícitas.
- `useState` de `source` inicia en `"auto"`.
- Sin cambios de layout ni de tipos de respuesta.

## Modelo de datos

Sin cambios. Todos los formatos mapean al `FailureRecord` existente
(`test_name, error_type, message, trace, project, source`). El único cambio de esquema
es ampliar el `CHECK` de `test_runs.source`.

## Manejo de errores

| Situación | Resultado |
|---|---|
| `source="auto"` y el detector no reconoce el contenido | `ValueError` → **400** "No se reconoció el formato; selecciónalo manualmente." |
| Archivo inválido (XML/JSON corrupto) o que no casa con el formato forzado | `ValueError` del parser → **400** con detalle |
| `source` explícito no soportado | `ValueError` → **400** |
| Reporte válido sin fallos | `ingested=0, known=0, novel=0` (200), como hoy |

## Estrategia de testing (TDD)

- **Fixtures reales mínimas** por formato en `tests/fixtures/` (un reporte con 1-2
  fallos y, donde aporte, 1 test pasado para verificar que se ignora).
- **Un test por parser** (`tests/test_parse_<fmt>.py` o un `test_parsers.py`
  parametrizado): verifica nº de `FailureRecord`, mapeo de campos clave y que los
  pasados se ignoran.
- **`tests/test_detect.py`**: cada uno de los 7 formatos se detecta correctamente, más
  un caso **ambiguo** controlado y uno de **basura** (→ `None`).
- Todo el núcleo es **puro** (sin BD ni LLM); corre en el CI backend. La ampliación del
  `CHECK` se cubre con una nota de migración; no requiere test de integración nuevo
  porque `ingest_run` no cambia.

## Decisiones de diseño

- **Enfoque híbrido (auto + override)**: el detector da la experiencia "sube y listo" y
  escala a N formatos; el override evita quedar bloqueado ante archivos ambiguos o
  formatos aún no reconocidos. El coste sobre auto-puro es una opción más en un `<select>`
  que ya existe.
- **Detección por contenido, no por extensión**: tres formatos son XML y cuatro son
  JSON; la extensión no distingue.
- **Reutilizar `FailureRecord`**: un bug de Jira (Slice 2) sí requerirá repensar el
  modelo, pero todos los reportes de test automáticos encajan en el record actual.
```
