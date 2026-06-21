# Capa LLM intercambiable + Análisis de causa raíz por familia

**Fecha:** 2026-06-21
**Estado:** Diseño aprobado (pendiente de plan de implementación)

## Contexto

Mnemo usa hoy un LLM local (Ollama / DeepSeek-R1) en un único punto: `LocalNarrator`
(`src/assurance/narrator.py`), que instancia `OllamaLLM` directamente y narra el veredicto
de un run. El campo `defect_families.root_cause` existe en el esquema pero **no se usa**.

Se quiere (1) que el LLM sea **intercambiable** por cualquier proveedor —local u
comercial— para que el proyecto escale a la política de cada cliente (privacidad total con
local 0 €, o más potencia con un comercial), y (2) una primera función de IA que aproveche
esa capa: **análisis de causa raíz por familia de defecto** con sugerencia de fix.

## Objetivo

Construir una capa `LLMProvider` configurable globalmente por entorno (Ollama / OpenAI-
compatible / Anthropic, extensible), migrar el `Narrator` a esa capa, y añadir un análisis
de causa raíz **bajo demanda y cacheado** que el LLM configurado genera para una familia.

## Alcance

**Incluido:**
- Capa `src/llm/`: `LLMProvider` (interfaz), proveedores Ollama/OpenAI/Anthropic, factory
  por entorno, helper `strip_reasoning`.
- Migración de `Narrator` para consumir `LLMProvider`.
- Análisis de causa raíz: prompt puro, `RootCauseAnalyzer`, persistencia en `root_cause`,
  endpoint `POST /v2/defects/{id}/root-cause`, botón en el frontend.
- Variables de entorno nuevas + dependencias `langchain-openai`, `langchain-anthropic`.
- Tests unitarios (TDD) + un test de integración para la persistencia.

**Fuera de alcance (ampliaciones futuras):**
- Configuración de LLM **por org** (la capa queda extensible; de momento es global).
- Contexto RAG/KB (Confluence/docs) dentro del prompt de causa raíz.
- Clasificación de severidad / detección de flaky / análisis cross-family.
- Background jobs / colas (el análisis es síncrono bajo demanda).
- Migrar el analyzer legacy `/v2/analyze` a la capa (queda preparado, no se toca aquí).

## Arquitectura

```
            ┌─────────────────────────────────────────┐
 env vars ──► get_llm_provider()  ──►  LLMProvider     │   (Ollama | OpenAI | Anthropic)
            └─────────────────────────────────────────┘
                         ▲                     ▲
                         │                     │
                  Narrator(provider)    RootCauseAnalyzer(provider)
                  (veredicto del run)   (causa raíz por familia)
```

Un único punto de selección (`factory`), consumidores agnósticos al proveedor. Añadir un
proveedor nuevo = una clase que implemente `LLMProvider`.

## Componentes

### Capa LLM (`src/llm/`)

- `provider.py`:
  ```python
  @runtime_checkable
  class LLMProvider(Protocol):
      def complete(self, prompt: str) -> str: ...
  ```
- `reasoning.py`: `strip_reasoning(text: str) -> str` elimina bloques `<think>…</think>`
  (regex `re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)`) y hace `.strip()`.
  Inocuo para salidas sin razonamiento.
- `providers/ollama.py`: `OllamaProvider(model, base_url)` — lazy `OllamaLLM(...).invoke(prompt)`.
- `providers/openai.py`: `OpenAIProvider(model, api_key, base_url=None)` — lazy
  `ChatOpenAI(model=, api_key=, base_url=)`; `complete` hace `.invoke(prompt)` y devuelve
  `.content`. Un `base_url` no vacío habilita endpoints compatibles (Azure, Groq, vLLM…).
- `providers/anthropic.py`: `AnthropicProvider(model, api_key)` — lazy
  `ChatAnthropic(model=, api_key=)`; `complete` devuelve `.content`.
- `factory.py`: `get_llm_provider() -> LLMProvider`. Lee `LLM_PROVIDER` (default `"ollama"`)
  y construye el proveedor con sus credenciales. Proveedor desconocido → `ValueError`.
  Una API key requerida ausente (openai/anthropic) → `RuntimeError` con mensaje claro.

Todos los imports de `langchain_*` se hacen **dentro** del método (lazy), como el actual
`LocalNarrator`, para no exigir las libs comerciales si no se usan.

### Config (`src/config.py`) + entorno

Variables nuevas:
```python
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", MODEL_NAME)   # default deepseek-r1:8b
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")  # vacío = OpenAI oficial
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
```
El default (`ollama` + `deepseek-r1:8b`) mantiene la baza 0 €/privado sin configurar nada.

### Migración del Narrator (`src/assurance/narrator.py`)

- `Narrator` (Protocol `summarize(verdict) -> str`) se conserva.
- `LocalNarrator` se reemplaza por `LLMNarrator(provider: LLMProvider)`: construye el mismo
  prompt actual y hace `strip_reasoning(self._provider.complete(prompt))`. (Se conserva un
  alias `LocalNarrator = LLMNarrator` si hay imports, o se actualiza el call-site.)
- El dep lazy `get_narrator()` en `src/api_v2.py` pasa a `LLMNarrator(get_llm_provider())`.
  Comportamiento idéntico cuando `LLM_PROVIDER=ollama`.

### Causa raíz (`src/assurance/root_cause.py`)

- `build_root_cause_prompt(family: dict, failures: list[dict]) -> str` **pura**: incluye
  `family.title`, `occurrence_count`, nº de proyectos distintos, y hasta **6** fallos
  representativos (test_name, error_type, `message[:300]`, primer frame del trace). Pide en
  español la causa raíz probable + 3-5 pasos de corrección, en **markdown** con secciones
  `## Causa raíz` y `## Pasos sugeridos`. Deja claro al modelo que solo ve síntomas (no el
  código fuente), así que los pasos son heurísticos.
- `RootCauseAnalyzer(provider: LLMProvider)` con `analyze(family, failures) -> str`:
  `strip_reasoning(provider.complete(build_root_cause_prompt(...)))`.

### Repositorio (`src/defects/repository.py`)

- `get_family_with_failures(*, user_id, defect_id) -> dict | None`: devuelve
  `{"family": {id, title, status, occurrence_count, root_cause}, "failures": [...]}` con
  `error_type, message, trace, project` por fallo (los que el prompt necesita), limitado a
  los más recientes (p. ej. 20), con check de membership (None si no existe / no miembro).
  Patrón idéntico a `get_lineage` (que no trae message/trace).
- `save_root_cause(*, user_id, defect_id, text) -> bool`: `update defect_families set
  root_cause = %s where id = %s` con guard de membership (`exists(... memberships ...)`);
  devuelve si se actualizó.

### Endpoints (`src/api_v2.py`)

- `POST /v2/defects/{defect_id}/root-cause?regenerate=false` → `RootCauseResponse`:
  carga la familia (404 si None); si `root_cause` está cacheado y `not regenerate`, lo
  devuelve con `cached=true`; si no, `RootCauseAnalyzer(get_llm_provider()).analyze(...)`,
  `save_root_cause`, devuelve `cached=false`.
- `GET /v2/defects/{defect_id}` (lineage) incluye el `root_cause` cacheado (o null).
- Deps lazy: `get_root_cause_analyzer()` = `RootCauseAnalyzer(get_llm_provider())`.

### Modelos Pydantic (`src/multitenant_models.py`)

```python
class RootCauseResponse(BaseModel):
    defect_id: str
    root_cause: str
    cached: bool
```
`DefectLineageResponse` gana `root_cause: Optional[str] = None`.

### Frontend (`frontend/src/app/app/defects/page.tsx` + endpoints/types)

En el panel de linaje, botón **"Analizar causa raíz"** → `POST /v2/defects/{id}/root-cause`;
muestra el resultado como markdown con un disclaimer "sugerencia generada por IA, revísala"
y un botón "Regenerar". Tipo `RootCauseResponse` + función cliente `analyzeRootCause`.
Render markdown: `react-markdown` (nueva dep frontend) o, si se prefiere sin dep, un render
pre-formateado simple — decisión del plan.

## Manejo de errores / degradación

| Situación | Resultado |
|---|---|
| Familia inexistente / no miembro | **404** (analyzer no se invoca) |
| Usuario no miembro (save) | **403** |
| Proveedor LLM caído / API key inválida / timeout | **503** "el análisis IA no está disponible" (sin filtrar credenciales) |
| `LLM_PROVIDER` desconocido | `ValueError` → **500** al arrancar el dep (config de despliegue) |
| API key requerida ausente | `RuntimeError` con mensaje claro → **503** |

El veredicto y la narrativa siguen degradando como hoy (narrativa → None si el LLM falla).

## Seguridad

- Las API keys comerciales viven solo en el entorno del despliegue (`.env`), nunca en BD ni
  en respuestas/logs. Los errores del proveedor se devuelven con mensaje genérico (no se
  refleja la excepción cruda que podría contener cabeceras/keys).
- El análisis hereda el aislamiento por membership (la familia se carga con el guard).

## Testing (TDD)

- `strip_reasoning`: quita `<think>…</think>` (incl. multilínea); deja intacto el resto.
- `factory`: con `LLM_PROVIDER` ∈ {ollama, openai, anthropic} y los clientes `langchain_*`
  monkeypatcheados, devuelve la clase correcta; proveedor desconocido → `ValueError`; key
  ausente → `RuntimeError`.
- Cada provider: con el cliente subyacente mockeado, `complete` llama `invoke` y extrae el
  texto (str para Ollama, `.content` para chat models).
- `build_root_cause_prompt`: contenido esperado y truncado a 6 fallos / `message[:300]`.
- `RootCauseAnalyzer` y `LLMNarrator`: con un `FakeProvider` (devuelve texto fijo, incl. un
  `<think>` para verificar que se limpia).
- Repo (integración): `save_root_cause` + `get_family_with_failures` devuelven el texto y el
  membership rechaza a no-miembros.
- Endpoint: con analyzer mock — genera+cachea, devuelve cache sin regenerar, `regenerate`
  re-genera, y degradación a 503 cuando el provider lanza.
- Frontend: validado por el CI (typecheck/lint/build).

## Decisiones de diseño

- **Interfaz mínima `complete(prompt)->str`**: el común denominador de todo LLM; mantiene
  los providers triviales y los consumidores agnósticos. (Streaming/structured output son
  ampliaciones futuras.)
- **Markdown** como formato de salida (robusto con LLM local; sin parsing frágil de JSON).
- **Default ollama**: preserva la baza 0 €/privado sin configuración.
- **Imports lazy** de las libs comerciales: no se exigen si no se usan (despliegue mínimo
  on-prem sigue solo con Ollama).
- **Bajo demanda + cache** en `root_cause`: sin coste si no se pide; sin infra de jobs.
