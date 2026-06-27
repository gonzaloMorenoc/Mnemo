# 03 — Seguridad y Multitenancy (post-Bloque B)

Auditoría adversarial de seguridad y aislamiento multi-tenant de Mnemo Autopilot tras el Bloque B
(rama `main`, HEAD `6929d77`). Foco: invariante RLS, membership-gating de los endpoints/repos nuevos,
exfiltración vía LLM (`ALLOW_EXTERNAL_LLM`), integridad del certificado firmado Ed25519, inyección de
prompts, secretos, validación de input y authz (admin vs member).

Cada hallazgo lleva `archivo:línea`, severidad (Crítico/Alto/Medio/Bajo), impacto y fix.
Esfuerzo: S < ½d · M ≈ 1–2d · L > 2d.

Método: lectura del código (solo lectura), 17 migraciones, 4 sub-auditorías en paralelo
(membership-gating, exfiltración LLM, camino firmado, inyección de prompts) y verificación manual
directa de cada hallazgo Crítico/Alto contra el archivo:línea.

---

## Veredicto

**Apto para un piloto con UN cliente real, condicionado a 3 fixes de severidad Alta — ninguno Crítico.**

El núcleo es sólido y se nota el endurecimiento de las dos tandas previas:

- **Aislamiento multi-tenant: sin fisuras explotables hoy.** Las 17 tablas `public` tienen `enable` +
  `force` RLS + policy (el invariante que la auditoría del 2026-06-25 cazó sin `force` ya está corregido
  en `016`). Y, sobre todo, **todos** los endpoints y métodos de repo del Bloque B aplican el chequeo de
  membership a nivel de app contra el `org_id` del **recurso** (no contra input del cliente), que es el
  patrón correcto frente a IDOR. No encontré ninguna fuga cross-tenant explotable en briefing, ask,
  root-cause, `list_actions_for_run` ni la búsqueda semántica de familias.
- **Gate de exfiltración LLM: arquitectónicamente correcto.** `get_llm_provider()` es el único punto que
  construye proveedores externos y respeta `ALLOW_EXTERNAL_LLM`; los SDK de Anthropic/OpenAI solo se
  importan dentro de sus providers, instanciados solo por la factory. Las 11 invocaciones de LLM
  (judge, nl_query, briefing, narrator, root_cause, ai_repair, explainer, tiebreaker, certificado +
  legacy) pasan por el gate o son local-only. La degradación nunca cae a un proveedor externo.
- **Cripto del certificado: bien usada.** Canonicalización determinista (claves ordenadas, sin espacios,
  UTF-8); la clave privada Ed25519 nunca se loguea, ni se serializa, ni se devuelve por API; clave vacía
  → `raise`, no firma débil; certificado *append-only* (grant solo `select, insert`); `risk_score`
  puramente determinista (sin término LLM).

Pero hay **3 hallazgos Altos** que deben arreglarse antes de exponer a un cliente, más deuda Media/Baja:

1. **[Alto] El LLM-judge puede mover el veredicto FIRMADO** (`apto`→`apto-con-reservas`). Solo en sentido
   conservador, pero rompe el invariante "el veredicto es determinista" que el propio producto promete, e
   introduce no-determinismo (y un vector de inyección) en un artefacto firmado.
2. **[Alto] El gate de aprobación humana de Nivel 2 lo puede disparar cualquier `member`/`viewer`** — no
   exige rol admin. Un usuario de baja confianza puede aprobar que se escriba **código generado por IA en
   el repo del cliente** (PR) o se cree un Issue. Es el residuo no corregido de A1 (2026-06-25).
3. **[Alto] Trazado LangSmith fuera del gate `ALLOW_EXTERNAL_LLM`.** `.env.example` envía
   `LANGCHAIN_TRACING_V2=true`: cualquiera que lo copie y ponga una API key exfiltra TODOS los prompts
   (trazas de error del cliente, contexto de KB) a `api.smith.langchain.com`, saltándose por completo la
   promesa "privado por diseño".

Recomendación operativa: arreglar los 3 Altos (todos S–M) y la validación de longitud de input (S) antes
del piloto; el resto (Medios/Bajos) es endurecimiento que puede ir en paralelo. No hay bloqueante Crítico.

---

## RLS por tabla

Las 17 tablas `public` del esquema, con su estado `enable` / `force` / policy. **Todas cumplen el
invariante.** Query de verificación recomendada como gate de release (debe dar `t,t` en las 17):

```sql
select relname, relrowsecurity, relforcerowsecurity
from pg_class
where relnamespace = 'public'::regnamespace and relkind = 'r';
```

| Tabla | enable | force | policy (tipo) | Notas |
|---|:--:|:--:|---|---|
| `profiles` | ✅ 001:253 | ✅ 016:6 | select/insert/update own | por-usuario |
| `organizations` | ✅ 001:254 | ✅ 016:7 | select member / insert creator / update admin / delete owner | authz por rol ✅ |
| `memberships` | ✅ 001:255 | ✅ 016:8 | select visibility / insert·update·delete admin | define la autorización |
| `documents` | ✅ 001:256 | ✅ 016:9 | scope select/insert/update/delete | legacy KB |
| `chunks` | ✅ 001:257 | ✅ 016:10 | scope select/insert/update/delete | legacy KB |
| `embeddings` | ✅ 001:258 | ✅ 016:11 | scope select/insert/update/delete | legacy KB |
| `analyses` | ✅ 001:259 | ✅ 016:12 | **solo select + insert** (001:421,428) | ver Bajo S-7 |
| `test_runs` | ✅ 002:55 | ✅ 002:58 | `for all` `is_org_member(org_id)` | ✅ |
| `failures` | ✅ 002:56 | ✅ 002:59 | `for all` `is_org_member(org_id)` | ✅ |
| `defect_families` | ✅ 002:57 | ✅ 002:60 | `for all` `scope='global' OR is_org_member` | ver Bajo S-5 |
| `test_results` | ✅ 007:36 | ✅ 007:38 | `for all` `is_org_member(org_id)` | ✅ |
| `dom_snapshots` | ✅ 007:37 | ✅ 007:39 | `for all` `is_org_member(org_id)` | ✅ |
| `triage_verdicts` | ✅ 009:26 | ✅ 009:27 | `for all` `is_org_member(org_id)` | ✅ |
| `actions` | ✅ 010:24 | ✅ 010:25 | `for all` `is_org_member(org_id)` | ✅ |
| `org_integrations` | ✅ 013:12 | ✅ 013:13 | `for all` `is_org_member(org_id)` | RLS reparada en 013 |
| `certificates` | ✅ 014:19 | ✅ 014:20 | `for all` `is_org_member(org_id)` | grant solo select/insert (append-only) |
| `triage_corrections` | ✅ 015:17 | ✅ 015:18 | `for all` `is_org_member(org_id)` | ✅ |

**Conclusión RLS:** ninguna tabla `public` queda sin `enable`+`force`+policy. El Bloque B no añadió
tablas nuevas (las migraciones nuevas, `016` y `017`, solo hacen hardening RLS, índices, y un
`check`/columna en `actions`). El invariante de doble defensa (RLS + membership en app) se mantiene.

Observaciones (no incumplen el invariante):

- **`analyses` (legacy)** tiene policy de `select` e `insert` pero no de `update`/`delete`, aunque el grant
  sí incluye `update, delete` (001:443). Con `force` RLS y sin policy, esas operaciones quedan
  **denegadas por defecto** (default-deny) → no es una fuga, pero es una inconsistencia grant↔policy.
  Ver Bajo S-7.
- **`is_org_member`** (016:15) está bien definida: `stable`, `(select auth.uid())` para que el planner
  hoistee la subconsulta. Es la base de casi todas las policies `for all`.
- **`defect_families`** y `documents`/`chunks`/`embeddings` usan `scope='global'` como rama de lectura
  cross-org *por diseño* (aprendizaje compartido / KB global). Para `defect_families` es hoy una rama
  muerta (nunca se insertan familias `global`, solo `org` — `repository.py:113-114`). Ver Bajo S-5.

> Recordatorio de invariante (del MEMORY del proyecto): **el pooler de la app BYPASA RLS**. Por eso el
> RLS es defensa-en-profundidad (frente a PostgREST/anon-key/un futuro acceso con rol no-owner), y el
> control de aislamiento *real* en el camino de la app es el chequeo de membership en cada repo. Ambos
> están presentes; el `_set_claims` que ponen los repos (`request.jwt.claim.sub`) NO es control de
> seguridad y el código lo documenta así (`src/defects/repository.py:47-50`).

---

## Membership-gating

**No existe un helper compartido único**; el patrón es SQL inline repetido, en dos formas equivalentes y
ambas correctas:

1. **Pre-check explícito** (mutaciones / list-by-org): `select exists(select 1 from public.memberships
   where org_id=%s and user_id=%s)` → si `false`, `raise PermissionError` / `return []` / `return None`.
2. **`exists(...)` correlacionado al `org_id` del recurso** (lecturas/updates by-id): `... where
   <recurso>.id=%s and exists (select 1 from public.memberships m where m.org_id=<recurso>.org_id and
   m.user_id=%s)` → la fila es invisible salvo que el llamante sea miembro del org **del recurso**.

La forma (2) es la que neutraliza IDOR: la membership se comprueba contra el `org_id` de la fila, **no**
contra input del cliente. Los únicos helpers con nombre son `IntegrationsRepository._require_member` /
`_require_admin` (`src/jira/integrations_repository.py:37,46`) y `TenantKBRepository._is_org_member`
(`src/tenant_kb.py:118`).

Tabla por superficie del Bloque B:

| Superficie | Autenticado | org resuelto desde | Membership en `archivo:línea` | IDOR |
|---|:--:|---|---|:--:|
| `POST /v2/defects/ask` (`api_v2.py:921`) | ✅ :924 | body `AskRequest.org_id` (confiado-y-luego-chequeado) | `defects/repository.py:935-938` (pre-check, `[]` si no miembro) | No |
| `GET /v2/runs/{id}/briefing` (`api_v2.py:943`) | ✅ :946 | **de la fila del run** (no del cliente) | run `defects/repository.py:538`; cert `certify/repository.py:78`; actions `actions/repository.py:75` | No |
| `POST /v2/defects/{id}/root-cause` (`api_v2.py:717`) | ✅ :721 | **de la fila de la familia** | read `defects/repository.py:471-473`; save `:514-516` | No¹ |
| `GET /v2/certificates/{id}` (`api_v2.py:873`) | ✅ :876 | de la fila del cert | `certify/repository.py:78-79` | No |
| `ActionRepository.list_actions_for_run` (`actions/repository.py:68`) | n/a (repo) | del `org_id` de la acción | `actions/repository.py:75-76` (inline `exists`) | No |
| `AssuranceRepository.search_families_semantic` (`defects/repository.py:928`) | n/a (repo) | body `org_id`, pre-chequeado | `defects/repository.py:935-938` + query `scope='org' and org_id=%s` (`:942`) | No |
| `GET /v2/calibration/metrics` (`api_v2.py:702`) | ✅ | body/param org_id | `defects/repository.py:879-882` | No |
| `PATCH /v2/defects/{id}/label` (`api_v2.py:683`) | ✅ | de la fila de la familia | `defects/repository.py:842-845` | No¹ |

¹ Aplica la nota Bajo S-5 (rama `scope='global'`, hoy muerta).

**Análisis IDOR — no encontré fuga cross-tenant explotable.** Casos clave verificados:

- **briefing** toma solo `run_id` del path y resuelve el org **del run**; no hay `org_id` de cliente que
  falsificar, y las 3 lecturas (run, certificado, acciones) revalidan membership de forma independiente
  contra el `org_id` de cada fila. Un usuario del org A pasando el `run_id` del org B recibe `404`
  (`api_v2.py:954-955`), porque `get_run_assurance_data` devuelve `run=None`.
- **ask / search_families_semantic** aceptan `org_id` del body pero comprueban membership **antes** de
  devolver datos y además acotan la query vectorial a `scope='org' AND org_id=%s` — un `org_id` falsificado
  devuelve `[]`, no las familias de otro tenant. **La búsqueda semántica no mezcla filas `global`** → sin
  fuga vectorial cross-tenant.

### Hallazgo de authz por rol (Alto)

**[A-1] (Alto) El gate de Nivel 2 (approve/materialize/reject de acciones) no exige rol admin — cualquier
`member`/`viewer` puede disparar una escritura externa.** `src/actions/repository.py:113-185`
(`approve_action`, `materialize_action`, `mark_materializing`, `revert_to_approved`, `reject_action`) gatean
**solo** con `exists(... memberships ...)` — sin `role in ('owner','admin')`. La promesa central de
seguridad del producto es "Autopilot Nivel 2: nada externo sin aprobación humana"; pero la aprobación la
puede dar el rol de **menor** privilegio (la fila de `memberships` existe sea cual sea el rol, incluido
`viewer`). El impacto es máximo porque al aprobar se materializa, vía `ActionService._materialize`
(`src/actions/service.py:142-168`): un **Issue en el repo del cliente** (`create_issue`) o un **PR borrador
que escribe código generado por IA en el código de test del cliente** (`open_draft_pr` con
`old_str`/`new_str`, ver A-2). Esto es exactamente el residuo no corregido de A1 (auditoría 2026-06-25):
la parte de *configuración de integraciones* SÍ se endureció a admin (`integrations_repository.py:60,96`
para Jira y GitHub), pero la parte de *aprobación de acciones* se quedó en `is_org_member`.
**Fix (M):** comprobar `role in ('owner','admin')` en `approve_action`/`materialize_action`/`mark_materializing`/`reject_action` (o exponer `is_org_admin(org_id)` en SQL y usarla como en `integrations_repository`). Mínimo: admin para `approve`/`materialize`. Tests: `member` no puede aprobar.

---

## Exfiltración LLM

**El gate `ALLOW_EXTERNAL_LLM` es correcto y completo dentro del camino de proveedores.**
`src/llm/factory.py:20-24` lanza `RuntimeError` si `provider ∈ {openai, anthropic}` y `ALLOW_EXTERNAL_LLM`
no es `true`. Por defecto local (`config.py:13` `ollama`; `config.py:19` `ALLOW_EXTERNAL_LLM=false`). Los
SDK de Anthropic/OpenAI se importan SOLO dentro de `src/llm/providers/{anthropic,openai}.py`, y esos
providers se construyen SOLO en la factory (grep repo-wide: `AnthropicProvider(`/`OpenAIProvider(` solo en
`factory.py` y tests). **No hay segundo punto de construcción.**

Mapa de las 11 invocaciones de LLM y su ruta:

| Sitio (`archivo:línea`) | Cómo obtiene el provider | ¿Gated? |
|---|---|:--:|
| judge `src/ai/judge.py:26` | `generate_structured(provider=None)` → `generate.py:38` `get_llm_provider()` | ✅ |
| nl_query `src/ai/nl_query.py:26` | idem; endpoint `api_v2.py:936` `get_llm_provider()` | ✅ |
| briefing `src/ai/briefing.py:72` | idem; endpoint `api_v2.py:964` | ✅ |
| narrator `src/assurance/narrator.py:25` | inyectado; `api_v2.py:151-152` `get_llm_provider()` | ✅ |
| root_cause `src/assurance/root_cause.py:89` | idem; `api_v2.py:160-161` | ✅ |
| ai_repair `src/actions/ai_repair.py:38` | inyectado; `api_v2.py:255` `get_llm_provider()` | ✅ |
| self-heal explainer `src/actions/selfheal/explainer.py:31` | inyectado; `api_v2.py:245-246` | ✅ |
| tiebreaker `src/triage/tiebreaker.py:55` | `self._provider or get_llm_provider()` | ✅ |
| certificado (judge) `api_v2.py:287` | `get_llm_provider()` | ✅ |
| legacy `StructuredAnalyzer` `src/structured_analyzer.py:33` | `OllamaLLM` hardcoded | local-only |
| legacy `BugAnalyzer`/`RAGAS` `src/model.py:10`,`src/evaluator.py:19` | `OllamaLLM` hardcoded | local-only |

El fallback de `generate.py:36-46` es el linchpin y es correcto: con `provider is None`, llama a
`get_llm_provider()` dentro de try/except que **degrada a None** ante `RuntimeError`, en vez de saltar a un
proveedor externo hardcodeado. Embeddings: **locales** (`src/defects/embedder.py:20-22`,
`HuggingFaceEmbeddings` `all-MiniLM-L6-v2`); no hay `OpenAIEmbeddings` en el repo. Degradación: ante LLM
caído se baja a plantillas deterministas / None, nunca a externo (`nl_query.py:29`, `briefing.py:74`,
`root_cause.py:73`, `tiebreaker.py:57`, `ai_repair.py:40`). **Sin defaults externos baked-in**:
`.env.example:26` `LLM_PROVIDER=ollama`, `:31` `ALLOW_EXTERNAL_LLM=true` comentado; `docker-compose.yml`
pasa `LLM_PROVIDER` desde el entorno sin valor externo fijo.

### Hallazgos de exfiltración

**[E-1] (Alto) Trazado LangSmith fuera del gate `ALLOW_EXTERNAL_LLM`.** `.env.example:2-5` envía
`LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"` y un placeholder de
`LANGCHAIN_API_KEY` **sin comentar**. `src/config.py:5` ejecuta `load_dotenv()`. Cuando
`LANGCHAIN_TRACING_V2=true` con una key válida, LangChain auto-instrumenta **todas** las llamadas envueltas
en LangChain (provider Ollama vía `langchain_ollama`, embeddings HuggingFace, y los analizadores legacy
—incluido `StructuredAnalyzer`, vivo en `api_v2.py:330`) y envía **prompt + respuesta completos** a un
tercero, **saltándose por completo** `get_llm_provider()` y `ALLOW_EXTERNAL_LLM`. Es decir: incluso en la
config "local por defecto", los prompts con trazas de error del cliente y snippets de KB pueden salir de la
infra. Mitigantes: el `.env` real está gitignored (`.gitignore:41`) y NO está trackeado (verificado:
`git ls-files .env` no devuelve nada), así que la key real no está en el repo; `.env.example:35` lleva un
aviso. **Pero el archivo de ejemplo commiteado induce la fuga** por defecto a quien copie
`.env.example`→`.env`. Nota: los providers Anthropic/OpenAI por SDK directo NO son trazados por LangChain,
así que este vector es específico de las rutas LangChain (Ollama/legacy/embeddings).
**Fix (S):** comentar `LANGCHAIN_*` en `.env.example` (default-off, como el bloque de LLM externo); y
considerar un assert en arranque: si `ALLOW_EXTERNAL_LLM` no está, `LANGCHAIN_TRACING_V2` debe ser falsy
(falla cerrado, para que el trazado no socave la garantía de privacidad).

**[E-2] (Alto, diseño) El AIRepairActuator manda el código fuente del cliente entero bajo el MISMO único
flag, sin truncar y sin consentimiento específico para código.** `src/actions/service.py:68`
`source = codehost.read_file(ctx["file"])` lee el **archivo de test completo** del repo del cliente, y
`src/actions/ai_repair.py:37` lo mete **verbatim** en el prompt (`{"id":"test_source","content":source}` —
sin recorte, a diferencia de root_cause que capa mensajes a 300 chars). Está correctamente *gated* por
`get_llm_provider()` (no hay bypass), pero lo gobierna el **mismo** `ALLOW_EXTERNAL_LLM` que usos de baja
sensibilidad (la narrativa del veredicto). No hay un tier de consentimiento más conservador para
"exfiltrar mi código fuente de test" frente a "resumir el triaje". Si el cliente activa LLM externo para
resúmenes, *también* consiente el envío de su código fuente (con sus fixtures, URLs internas, posibles
credenciales hardcodeadas o PII en datos de test). El sanitizador **no** se aplica al código fuente
(ver I-2). **Fix (M):** gatear los prompts que llevan código fuente tras un opt-in distinto
(p.ej. `ALLOW_EXTERNAL_SOURCE_CODE`), o como mínimo documentar y limitar (truncar/recortar) lo que se
envía.

**[E-3] (Bajo) Analizadores legacy ignoran `LLM_PROVIDER` (hardcoded `OllamaLLM`).**
`structured_analyzer.py:33`, `model.py:10`, `evaluator.py:19`. Local-only → sin exfiltración externa, pero
saltan la factory por completo y son la principal superficie que el trazado LangSmith (E-1) capturaría.
`StructuredAnalyzer` está vivo en `POST /v2/analyze` (`api_v2.py:330`). **Fix (S):** enrutar por la
factory o marcar explícitamente como local-only intencional.

---

## Camino firmado (certificado Ed25519)

**El núcleo cripto es correcto** (verificado en `src/certify/signing.py`, `certificate.py`, `service.py`,
`repository.py`, `gate.py` y la migración 014):

- **Canonicalización determinista**: `signing.py:12-15` `json.dumps(sort_keys=True,
  separators=(",",":"), ensure_ascii=False).encode("utf-8")`. El blob firmado incluye **todo** el
  certificado (verdict, risk_score, breakdown, evidence, sign_offs, self_eval — `certificate.py:104-118`);
  la firma cubre el payload entero, no una parte.
- **Clave privada protegida**: `MNEMO_SIGNING_PRIVATE_KEY` (`config.py:78`). No se loguea, no se serializa
  en el cert, no se devuelve por ningún endpoint (grep de logging/echo de config: ninguno). Solo la
  **firma** y la **clave pública** son user-facing. Sin fuga.
- **Clave vacía → falla cerrado**: `signing.py:19-20` `raise SigningKeyMissing` (HTTP 503 en
  `api_v2.py:852`). No firma con clave débil/por-defecto.
- **`risk_score` determinista**: fórmula lineal sobre categorías de triaje, **sin término LLM**
  (`certificate.py:95-96`).
- **Append-only**: `014_certificates.sql:24` concede solo `select, insert`; no hay `UPDATE`/`DELETE` de
  certificados en todo `src/` (verificado por grep). La policy es `for all` pero Postgres exige *privilegio
  + policy*, y el privilegio de update/delete no existe.

### Hallazgos del camino firmado

**[C-1] (Alto) El LLM-judge puede mover el veredicto FIRMADO (`apto` → `apto-con-reservas`).** Es el
hallazgo central y rompe el invariante explícito "la narrativa puede ser de IA, pero el VEREDICTO/SCORE
debe ser determinista". Cadena verificada:

`service.py:35` `compute_ai_eval(...)` → `judge.py:48` `judge_output()` → `judge.py:26`
`generate_structured()` **(llamada LLM)** → devuelve `faithfulness` → `service.py:39`
`compute_self_eval(..., ai_eval=ai_eval)` → `certificate.py:38-39`:
```python
if ai_eval is not None and ai_eval.get("faithfulness", 1.0) < _LOW_FAITHFULNESS:  # 0.5
    confidence = "low"
```
→ `certificate.py:93` `compute_verdict(verdicts, confidence=self_eval["confidence"])` → `certificate.py:66-68`:
```python
if confidence == "low":
    return "apto-con-reservas"   # en vez de "apto"
```
→ firmado en `service.py:47-48`.

Matices y por qué es **Alto** (no Crítico): el LLM solo mueve el veredicto en sentido **conservador**
(`apto`→`apto-con-reservas`) y solo cuando el resto del triaje es benigno (sin reales/mantenimiento, nada
pendiente de aprobación); **no** puede fabricar `apto` desde `no-apto` ni tocar `risk_score`. Pero (a)
introduce **no-determinismo** en un artefacto **firmado** (dos runs con triaje idéntico pueden producir
veredictos firmados distintos según el "humor" del modelo / drift), y (b) abre un **vector de inyección**:
`judge.py:45-46` mete `evidence_bundle` (contenido no confiable: mensajes/trazas) en el contexto del juez,
y la salida del juez dirige el veredicto firmado — un fallo malicioso podría forzar `faithfulness≥0.5` para
**suprimir** una rebaja merecida (debilita la garantía de "certificado honesto"). El objeto `ai_eval`
(números autogenerados por LLM) además vive dentro del `self_eval` firmado (`certificate.py:50,117`).
**Fix (M):** sacar al juez del `confidence` que alimenta `compute_verdict`; mantener `ai_eval` como campo
**reportado y claramente no vinculante** dentro de `self_eval`, pero computar el `confidence`/`verdict`
firmados solo desde calibración determinista + triaje.

**[C-2] (Medio) El veredicto/score firmados se duplican en columnas DB NO firmadas, y la API sirve las
columnas.** `save_certificate` escribe `verdict` y `risk_score` como columnas propias *además* del
`canonical_json` (`certify/repository.py:58-65`; esquema `014:9-11`). El endpoint de lectura
`GET /v2/certificates/{run_id}` devuelve **los valores de columna**, no los re-derivados del JSON firmado
(`api_v2.py:885-887` ← `repository.py:88-89`). Cualquiera con acceso de escritura a la DB (o un futuro bug)
podría poner `verdict='apto'` en la columna mientras el `canonical_json` firmado sigue diciendo `no-apto`;
la API reportaría `apto` y la firma seguiría validando contra el JSON intacto. Las columnas son duplicado
de conveniencia/índice fuera de la frontera de integridad. **Fix (S):** derivar el `verdict`/`risk_score`
de la API desde `canonical_json`, o añadir un `CHECK`/trigger que asegure
`verdict = canonical_json->>'verdict'` y `risk_score = (canonical_json->>'risk_score')::int`.

**[C-3] (Medio) El gate recomputa el veredicto por su cuenta y NUNCA verifica el certificado firmado.**
`GateService.publish` (`src/certify/gate.py:33-52`) **recomputa** el veredicto desde cero con
`compute_verdict(verdicts, confidence=...)` (`gate.py:44-46`) y lo publica al check-run del codehost; nunca
carga el certificado guardado ni llama a `verify_payload`. Consecuencias: (a) el gate computa `confidence`
**sin** `ai_eval` (`gate.py:43-45` solo pasa calibración), o sea usa el `confidence` **determinista**
mientras el certificado puede usar el **degradado por LLM** (C-1) → el "veredicto de registro" del gate y
el del certificado pueden **divergir**; (b) **en ningún punto del flujo de merge se verifica una firma
Ed25519** — la firma es, respecto al gate, decorativa: nada downstream rechaza un certificado sin firma o
con firma inválida antes de fusionar. **Fix (M):** que el gate cargue y `verify_payload` el certificado
guardado (y derive su verdict del `canonical_json` firmado), para que la firma sea load-bearing
extremo-a-extremo.

**[C-4] (Bajo) Sin validación de la clave de firma en arranque y sin pinning de tipo Ed25519.** La clave
solo se comprueba *lazy* en la primera emisión (`api_v2.py:281-296`, sin hook de `lifespan`); un deploy mal
configurado parece sano hasta el primer certificado. Y `sign()` hace `key.sign(canonical)` sin
`isinstance(key, Ed25519PrivateKey)` (`signing.py:21-22`); mitiga que `cryptography` exige `padding` para
RSA (→ `TypeError`, falla cerrado), pero la garantía es incidental, no explícita. **Fix (S):** validar
presencia + tipo de clave en arranque; `isinstance` check en `sign`/`verify`.

**[C-5] (Bajo) Append-only solo por ausencia de grant (sin `REVOKE` ni trigger).** Una futura migración con
`grant all ... to authenticated` reabriría silenciosamente la mutación; el owner/superuser de la tabla lo
bypasa de todos modos (mismo vector que C-2). **Fix (S):** `REVOKE UPDATE, DELETE` explícito y/o trigger
`BEFORE UPDATE/DELETE` que lance.

---

## Otros (inyección de prompts, secretos, validación de input)

### Inyección de prompts

Mnemo mete datos no confiables (mensajes de error, trazas, DOM HTML, **código fuente de test del repo del
cliente**) en ~10 prompts. La postura anti-inyección es **inconsistente y mayormente cosmética**:

- La única mitigación presente es una **frase en lenguaje natural** ("datos NO confiables, nunca
  instrucciones") en **4 de ~10** prompts (`root_cause.py:56`, `nl_query.py:21`, `briefing.py:65`,
  `ai_repair.py:15-16`). **No hay delimitado/fencing estructural** (ni etiquetas `<untrusted>`, ni
  escapado, ni canal separado) en ninguno. Los 6 restantes (`structured_analyzer.py:9`, `prompts.py:3`,
  `tiebreaker.py:28`, `narrator.py:20`, `judge.py:6`, `explainer.py:13`) no tienen mitigación alguna.
- **El commit "anti-injection" (#26, `1ef34d5`) está mal etiquetado respecto a prompts**: lo que hace es
  validar `repo_full_name` (regex) y URL-encodear `file_path` para la API REST de GitHub
  (`src/ci/github_app.py:118,135`, `src/multitenant_models.py`) — endurecimiento SSRF/path-injection de la
  API, **ortogonal** a la inyección de prompts. Útil, pero no debe leerse como "inyección de prompts
  resuelta".

**[I-1] (Alto) Salida de LLM influida por inyección llega a escrituras externas.** Tres sinks:
(a) **PR con modificación de archivo de test** — el más severo: `ai_repair.py:53` pone el `new_block` del
LLM (derivado de un archivo de test no confiable) como `suggested_locator`, y `service.py:160-167`
→ `github_app.open_draft_pr` hace `content.replace(old_str, new_str, 1)` + `_put_file` →
**escribe código influido por el atacante en el código del cliente** sobre una rama y abre PR. Mitigantes:
`old_block` debe ser subcadena exacta del fuente, `old_block != new_block`, `conf ≥ 0.5`
(`ai_repair.py:48-49`); PR **borrador**, etiquetado "NO auto-validado / nunca auto-merge", y requiere
`approve_action` humano. **Pero** el revisor revisa contenido fabricado por el atacante, la restricción de
subcadena solo fuerza que el parche *toque* código real (no que sea benigno), y A-1 permite que apruebe el
rol de menor privilegio. (b) **Jira/GitHub Issue**: el texto de root-cause del LLM (`ticket.py`) va al
`body` del Issue tal cual (markdown/links no se limpian). (c) **PR body**: `_self_heal_body`
(`service.py:11-33`) interpola `reasoning` del LLM. **Fix (M):** fencing estructural de lo no confiable en
los prompts; sanitizar/escapar la salida del LLM antes de un write externo; + A-1 (rol admin para
aprobar).

**[I-2] (Medio) El sanitizador es solo-PII y solo-ingesta; NO cubre vectores de inyección ni se aplica a
DOM/código/pregunta NL.** `src/sanitizer.py` redacta email/IP/URL/secret/path/user/hostname (+ guarda
ReDoS, cap 20k). Es un **redactor de PII/secretos, no un filtro de inyección** (no toca `<think>`, "ignore
previous instructions", etc.). Se aplica en ingesta a `message`/`trace` (`defects/ingestion_service.py:55`,
`jira/ingestion_service.py:30`, `ci/ingestion_service.py:27`), pero **NO** a: el **DOM** (self-heal/
explainer; grep `sanitize` en `src/actions/` = 0), el **código fuente** leído de GitHub
(`service.py:68`→`ai_repair.py:37`), la **pregunta NL** (`/v2/defects/ask`), ni `error_log` de
`/v2/analyze`. Implicación adicional: secretos dentro de un DOM o de un archivo de test **no se redactan**
antes de ir a un LLM externo (relevante con E-2). **Fix (M):** aplicar el sanitizador (o uno específico)
a DOM/código antes del prompt; añadir un pase anti-inyección.

**[I-3] (Bajo) Parseo de salida JSON razonablemente seguro, pero validación de tipos ad hoc.**
`generate.py` usa `json.loads` del slice `{...}` con try/except, **sin `eval`**, y hace whitelist de claves
al schema (descarta claves inesperadas del modelo) — bien. Pero no valida **tipos** ahí; cada caller
re-valida por su cuenta (`judge._clamp`, `root_cause` clamp/coerce, `briefing`/`nl_query` isinstance) — no
es un schema enforcement central. `tiebreaker.parse_category` es buen patrón defensivo (whitelist de 4
categorías; si aparecen las 4 → None, trata el "eco de instrucciones" como no-decisión). `strip_reasoning`
(`src/llm/reasoning.py`) solo se aplica en los 3 prompts de texto libre, no en `generate_structured`.
**Fix (S):** validación de tipos por schema en `generate_structured`.

**Punto positivo:** el camino del **certificado firmado** está bien aislado de la narrativa: el juez solo
devuelve 2 floats clampados (`judge.py:30`), ningún texto libre de LLM entra en el `canonical_json`, y el
juez solo puede **degradar** confianza (no inflar) — la única grieta es C-1 (que el float degrade el
veredicto firmado).

### Secretos

- **`.env` (config activa, gitignored, NO trackeado — verificado)**: contiene la key real de LangSmith
  (ver E-1). No está en el repo; el riesgo es la inducción vía `.env.example`. **Sin secretos hardcodeados
  en código fuente** (grep de `sk-…`, `ghp_…`, PEM, JWT en `src/`/`scripts/` = 0).
- **[S-6] (Bajo) `.env.docker` está commiteado con secretos de demo** (`JWT_SECRET`, `SERVICE_ROLE_KEY`,
  `MNEMO_SECRET_KEY`, `DEMO_PASSWORD`, `POSTGRES_PASSWORD`). Está **claramente marcado**
  `# === DEMO ONLY — NO usar en producción ===` y usa las keys públicas de ejemplo de Supabase, lo cual es
  práctica aceptable. Riesgo: que `MNEMO_SECRET_KEY`/`DEMO_PASSWORD`/`POSTGRES_PASSWORD` se reusen en un
  deploy real. Nota: el `CI_WEBHOOK_SECRET` y `MNEMO_SIGNING_PRIVATE_KEY` **no** están en `.env.docker`
  (bien). **Fix (S):** documentar rotación obligatoria; nunca reusar estos valores fuera de la demo local.
- **CI (`.github/workflows/backend-ci.yml`)**: corre tests unitarios + `eval_ai.py` (golden, sin LLM
  vivo); **no expone secretos ni usa LLM externo**. Limpio.
- **Webhook CI HMAC (`src/ci/webhook_auth.py`)**: correcto — fail-closed si falta secreto/cabecera,
  `hmac.compare_digest` (tiempo constante). El tamaño de body está capado (`CI_MAX_BODY_BYTES`, anti-DoS).
  El aislamiento mono-org del webhook (`CI_SERVICE_ORG_ID`) rechaza artefactos con otro `org_id`.

### Validación de input (boundary de los endpoints nuevos)

Todos los bodies son modelos Pydantic (buena base), pero los **campos de texto libre que van a prompts no
tienen cota de longitud**:

| Endpoint | Modelo | Validación | Veredicto |
|---|---|---|---|
| `POST /v2/defects/ask` | `AskRequest` (`multitenant_models.py:272`) | `org_id:str`, **`question:str` SIN min/max** | **[S-3] Alto** |
| `GET /v2/runs/{id}/briefing` | path | `run_id:str` (sin formato); membership en repo | Bajo |
| `POST /v2/analyze` | `AnalyzeV2Request:16` | `error_log: min_length=10` **SIN max_length**; `top_k` 1..20 | **[S-4] Medio** |
| `POST /v2/integrations/jira` | `JiraConfigRequest` | `base_url/email/token/jql` `str` sin validar | Medio |
| `POST /v2/actions/{id}/reject` | `ActionRejectRequest` | `reason:str=""` sin cota | Bajo |

**[S-3] (Alto) `AskRequest.question` sin cota de longitud y concatenada cruda al prompt #6**
(`nl_query.py:24`, embebida en `embedder.embed` y en el contexto). Vector de DoS / prompt-stuffing
(amplificación de coste/tokens) **y** la principal superficie de inyección NL. **Fix (S):**
`Field(min_length=1, max_length=…)`.

**[S-4] (Medio) `AnalyzeV2Request.error_log` sin `max_length`**, fluye cruda y sin sanitizar al prompt #1
(`structured_analyzer.py:61`). **Fix (S):** `max_length` + sanitizar.

---

## Hallazgos por severidad

### Crítico
*(ninguno)*

### Alto
| ID | Hallazgo | Ubicación | Fix |
|---|---|---|---|
| A-1 | Gate de Nivel 2 (approve/materialize/reject) sin rol admin: cualquier `member`/`viewer` puede disparar PR/Issue (incl. escribir código IA en el repo del cliente) | `src/actions/repository.py:113-185` | rol `('owner','admin')` en approve/materialize/reject (M) |
| C-1 | El LLM-judge mueve el veredicto **firmado** (`apto`→`apto-con-reservas`) — rompe el invariante de determinismo; no-determinista + inyectable vía evidencia del juez | `service.py:35`→`judge.py:48`→`certificate.py:38,66,93` | sacar el juez del `confidence` que firma; `ai_eval` solo reportado (M) |
| E-1 | Trazado LangSmith fuera del gate: `.env.example` envía `LANGCHAIN_TRACING_V2=true` → exfiltra todos los prompts a un tercero | `.env.example:2-5`; `config.py:5` | comentar `LANGCHAIN_*`; assert arranque (S) |
| E-2 | AIRepair manda el código fuente del cliente entero (sin truncar) bajo el mismo único `ALLOW_EXTERNAL_LLM` | `service.py:68`+`ai_repair.py:37` | tier de consentimiento aparte para código (M) |
| I-1 | Salida de LLM influida por inyección llega a PR (escribe código), Issue y PR body | `ai_repair.py:53`→`service.py:160`→`github_app.py:64`; `ticket.py` | fencing + sanitizar salida + A-1 (M) |
| S-3 | `AskRequest.question` sin cota → DoS/prompt-stuffing + vector de inyección | `multitenant_models.py:272-274`; `nl_query.py:24` | `Field(max_length=…)` (S) |

### Medio
| ID | Hallazgo | Ubicación | Fix |
|---|---|---|---|
| C-2 | Veredicto/score firmados duplicados en columnas DB no firmadas; la API sirve las columnas (pueden divergir del blob firmado) | `certify/repository.py:58-65,88-89`; `api_v2.py:885`; `014:9-11` | derivar del `canonical_json` o CHECK/trigger (S) |
| C-3 | El gate recomputa el veredicto y nunca verifica la firma; puede divergir del cert; la firma no es load-bearing en el merge | `src/certify/gate.py:33-52` | cargar + `verify_payload` el cert guardado (M) |
| I-2 | Sanitizador solo-PII y solo-ingesta; no cubre inyección ni se aplica a DOM/código/pregunta NL | `src/sanitizer.py`; `src/actions/*` | sanitizar DOM/código + pase anti-inyección (M) |
| S-4 | `error_log` (`/v2/analyze`) sin `max_length`, crudo+sin sanitizar al prompt | `multitenant_models.py:16`; `structured_analyzer.py:61` | `max_length` + sanitizar (S) |
| S-8 | Config de integración Jira (`base_url/email/token/jql`) sin validación (más débil que la de GitHub) | `src/jira/integrations_repository.py:55`; `multitenant_models.py` | validar URL/email/longitud (S) |

### Bajo
| ID | Hallazgo | Ubicación | Fix |
|---|---|---|---|
| C-4 | Sin validación de la clave de firma en arranque; sin pinning de tipo Ed25519 | `config.py:78`; `signing.py:21-22`; `api_v2.py:281` | validar en arranque + `isinstance` (S) |
| C-5 | Append-only solo por ausencia de grant (sin `REVOKE`/trigger); owner bypasa | `014:22-24`; `certify/repository.py:11` | `REVOKE`/trigger explícito (S) |
| E-3 | Analizadores legacy ignoran `LLM_PROVIDER` (Ollama hardcoded; local-only) — superficie de E-1 | `structured_analyzer.py:33`; `model.py:10`; `evaluator.py:19` | enrutar por la factory (S) |
| I-3 | Parseo JSON sin validación de tipos central (ad hoc por caller); `strip_reasoning` no en `generate_structured` | `src/ai/generate.py` | validación por schema (S) |
| S-5 | Rama de lectura/escritura `scope='global'` en el camino de `defect_families` bypasa membership (hoy rama muerta: nunca se insertan familias `global`) | `defects/repository.py:411,471,514,844` (insert solo `org` en `:113-114`) | quitar/documentar la rama global antes de un feature de aprendizaje cross-org (S) |
| S-6 | `.env.docker` commiteado con secretos de demo (marcado DEMO ONLY; keys públicas de Supabase) | `.env.docker` | documentar rotación; no reusar en prod (S) |
| S-7 | `analyses` (legacy): grant `update,delete` sin policy (default-deny → no es fuga, pero inconsistente) | `001:421,428,443` | añadir policy o quitar el grant (S) |

---

### Controles positivos confirmados (para balance)

- Las 17 tablas `public` con `enable`+`force`+policy; invariante de doble defensa intacto.
- Membership-gating correcto en **todas** las superficies del Bloque B; sin IDOR explotable; búsqueda
  semántica acotada a `org` (sin bleed cross-tenant).
- Gate `ALLOW_EXTERNAL_LLM` completo en el camino de proveedores; embeddings locales; degradación nunca
  cae a externo; sin defaults externos baked-in.
- Cripto del certificado: canonicalización determinista, clave privada sin fuga, clave vacía falla
  cerrado, `risk_score` determinista, append-only en grant, sin UPDATE/DELETE en código.
- HMAC del webhook CI fail-closed y en tiempo constante; aislamiento mono-org del webhook
  (`CI_SERVICE_ORG_ID`); body capado anti-DoS.
- Self-heal/AI-repair tras aprobación humana, PR borrador, etiquetado "masking_risk / nunca auto-merge".
- Endurecimiento SSRF/path-injection de la API de GitHub (`repo_full_name` regex, `quote(file_path)`).
- Config de **integraciones** (Jira y GitHub) ya exige rol admin (`integrations_repository.py:60,96`).
