# Mnemo Autopilot — F3b: self-heal del locator (diseño)

**Fecha:** 2026-06-24 · **Fase:** F3b (segunda de F3, §6.1 del spec maestro) · **Rama:** `feat/mnemo-selfheal` (apilada sobre `feat/mnemo-actions`/PR #15, porque F3b depende del marco de acción de F3a; reapuntar a `main` cuando F3a mergee)

## Objetivo

Para un veredicto de **mantenimiento** (un locator se rompió porque el DOM cambió legítimamente), generar de forma **determinista** un **locator robusto** y el cambio propuesto, como `ActionProposal(kind="self_heal")` en estado `proposed`. El LLM solo refina la explicación / desempata candidatos ambiguos (opcional, degradable). El PR borrador real lo abre F3c.

## Decisiones (confirmadas)

- **Determinista manda, LLM opcional.** El parseo del DOM, la búsqueda del elemento, el ranking de candidatos y la generación del locator son **deterministas y auditables** (clave para el certificado de F4). El LLM (inyectado) solo añade prosa/desempate y **degrada** (si no está, se usa el top determinista + explicación por plantilla).
- **Parser HTML: BeautifulSoup4** (`bs4`, pure-Python, tolerante, on-premise). Nueva dependencia en `requirements.txt`.
- **`file`/`line` no se persisten** en `failures` (el reporter los envía pero el ingest no los guarda) → el payload de F3b lleva el cambio de locator; **resolver la línea exacta en el fichero de test es de F3c** (grep del selector roto en el repo). *(Follow-up opcional: persistir file/line en el ingest para un patch más preciso.)*

## Componentes (`src/actions/selfheal/`, archivos pequeños y puros)

### `selector.py`
`parse_broken_selector(error_message: str, trace: Optional[str]) -> Optional[BrokenSelector]` — extrae el locator del error de Playwright y lo clasifica. `BrokenSelector` (dataclass): `kind` (`css|testid|text|role`), `value` (str), `role`/`name` (opcionales, para `getByRole`). Soporta: CSS (`#id`, `.class`, `[attr=...]`, tag), `getByTestId('x')`, `getByText('x')`, `getByRole('button', {name:'x'})` (best-effort). `None` si no se reconoce ninguna forma soportada.

### `dom.py` (bs4)
- `find_element(soup, broken: BrokenSelector) -> Optional[Tag]` — aplica el selector roto al **DOM verde** para hallar el elemento "viejo" (CSS → `soup.select_one`; testid → `find(attrs={"data-testid": ...})`; text → búsqueda por texto; role → tag+role aproximado). `None` si no casa.
- `signature(el: Tag) -> ElementSignature` (dataclass): atributos estables del elemento — `tag`, `role` (explícito o implícito por tag), `text` (normalizado), `testid`, `aria_label`, `el_id`, `name`, `neighbor_texts` (textos de hermanos/ancestros cercanos para desambiguar).

### `locator.py`
`robust_locator(el: Tag) -> str` — genera el mejor locator Playwright/TS por **prioridad de robustez**: `getByRole('<role>', { name: '<text>' })` > `getByTestId('<testid>')` > `getByText('<text>')` > CSS (`#id` / `.class` / atributo). `robustness_rank(locator_kind) -> int` (para puntuar candidatos). Puro.

### `candidates.py`
- `find_candidates(failure_soup, sig: ElementSignature) -> List[Tag]` — busca en el **DOM rojo** elementos compatibles con la firma (mismo role/tag, texto o testid o aria-label parecidos).
- `rank(candidates, sig) -> List[ScoredCandidate]` — puntúa cada candidato por **similitud semántica** (coincidencia de texto/role/testid/aria + vecinos) **+ robustez** del locator generable (`robust_locator`/`robustness_rank`). Ordena desc. `ScoredCandidate`: `{element, locator, score, why}`.

### `explainer.py` — el LLM opcional del self-heal (NO es el de root-cause)
`SelfHealExplainer` (Protocol): `explain(*, broken_locator, suggested_locator, candidates) -> str` — prosa legible del cambio de locator / desempate, **distinta** del `RootCauseAnalyzer` (ese analiza familias de defecto, no locators). `LLMSelfHealExplainer(provider)`: prompt acotado (ve el locator roto + el sugerido + los candidatos top-N) → explicación; **degrada** (excepción → cae a la plantilla del actuador). `TemplateExplainer` (determinista, por defecto): explicación por plantilla sin LLM.

### `selfheal.py` — `SelfHealActuator(explainer=None)`
`propose(verdict, context) -> Optional[ActionProposal]`. Orquesta:
1. `parse_broken_selector(context.error, context.trace)` → broken (`None` → degrade).
2. `find_element(green_soup, broken)` → elemento viejo → `signature` (`None` → degrade).
3. `find_candidates(failure_soup, sig)` → `rank` → top (vacío → degrade).
4. `suggested = top.locator`.
5. `reasoning`: si hay `explainer` (LLM, opcional), lo usa; si es `None` o lanza → **explicación por plantilla** determinista (broken→suggested + por qué es más robusto).
6. `ActionProposal(kind="self_heal", payload={broken_locator, suggested_locator, candidates: top-N {locator,score,why}, reasoning}, summary)`.
**Degrada a `None`** (cuenta `skipped` en `ActionService`) en cualquier paso sin datos. **Nunca rompe** `propose_actions`.

## Datos — repo
`get_selfheal_context(*, user_id, failure_id) -> Optional[Dict]` (membership-gated) → `{error_message, trace, green_dom, failure_dom}`:
- `error_message`/`trace` de la fila `failures`.
- `green_dom` = `dom_snapshots` (`kind='last_green'`) del test/proyecto; `failure_dom` = `kind='failure'` (mismo patrón que `get_triage_inputs`).
`None` si no es miembro / no hay datos.

## Wiring — `ActionService`
- El mapa de actuadores gana **`"maintenance": SelfHealActuator(explainer=<LLMSelfHealExplainer perezoso>)`** (registrado en `get_action_service`, con el explainer construido de forma perezosa para que una mala config del LLM degrade a plantilla en vez de romper el singleton; el `_context_for` de `maintenance` llama a `get_selfheal_context` y arma `{error, trace, green_dom, failure_dom}`).
- `get_run_actionable_verdicts` ya devuelve `maintenance` (no se filtra); el `failure_id` de la fila alimenta `get_selfheal_context`.
- El branch `proposal is None → skipped` (ya existente en F3a) cubre la degradación del self-heal.

## Alcance MVP (§6.1 del spec maestro)
Un locator roto por cambio de atributo/texto/estructura → locator robusto. Formas soportadas: CSS / `getByTestId` / `getByText` / `getByRole`-por-nombre (best-effort). **Roadmap (degrada):** Page Objects, multi-fichero, semántica completa de `getByRole`/ARIA, Selenium/Cypress.

## Manejo de errores / degradación
- Sin `green_dom` o `failure_dom`, selector no parseable, elemento viejo no hallado, o sin candidatos → `propose` devuelve `None` → `skipped`. Nunca excepción.
- `analyzer` (LLM) ausente o que lanza → top candidato determinista + explicación por plantilla.
- bs4 ante HTML roto → tolerante; si aun así falla el parseo → `None`.
- **Nivel 2 intacto:** el self-heal solo **propone**; nada se materializa sin `approve` (F3a). `NullCodeHost` no escribe nada.

## Testing (TDD; todo puro salvo el método de repo)
- **`selector.py`**: cada forma (css/testid/text/role) + no-reconocida → `None`.
- **`dom.py`**: `find_element` por cada forma sobre HTML verde de ejemplo; `signature` extrae role/text/testid/aria/vecinos.
- **`locator.py`**: prioridad de robustez (un elemento con role+name → getByRole; con testid → getByTestId; etc.).
- **`candidates.py`**: dado un DOM rojo con el elemento renombrado, lo encuentra y rankea por encima de distractores.
- **`selfheal.py`** (caso e2e con fixtures verde/rojo): botón "Checkout" cuyo `#id` cambió → `suggested_locator = getByRole('button', { name: 'Checkout' })`; caminos de degradación → `None`; LLM mockeado (refina) y ausente (plantilla).
- **repo** `get_selfheal_context` (integración Postgres): recupera error+DOMs; no-miembro → `None`.
- **`ActionService`** (mockeado): `maintenance` → SelfHealActuator con el context correcto; `None` → `skipped`.

## Fases (tareas del plan)
1. `bs4` en requirements + `selector.py` (`parse_broken_selector`) + tests.
2. `dom.py` (`find_element` + `signature`) + tests.
3. `locator.py` (`robust_locator` + `robustness_rank`) + tests.
4. `candidates.py` (`find_candidates` + `rank`, usa `locator`) + tests.
5. `explainer.py` (`SelfHealExplainer`/`LLMSelfHealExplainer` degradable/`TemplateExplainer`) + `selfheal.py` (`SelfHealActuator`, orquesta + degrada) + tests.
6. Repo `get_selfheal_context` (integración) + `ActionService` `maintenance`→SelfHeal + registro en `get_action_service` + tests.

## Fuera de alcance (YAGNI / fases posteriores)
- **GitHub App / PR borrador real + resolución de file:line** → **F3c**.
- Page Objects, multi-fichero, Selenium/Cypress, semántica ARIA completa → roadmap.
- Persistir `file`/`line` en el ingest → follow-up opcional.
- Gate + certificado → **F4**. Lazo de aprendizaje (un self-heal mergeado refuerza la estrategia) → **F5**.
