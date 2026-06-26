# Mnemo — B4: reparación IA más allá del locator (diseño)

**Fecha:** 2026-06-26 · **Bloque:** B (la IA como protagonista), apuesta 4 · **Spec maestro:** `docs/superpowers/specs/2026-06-26-mnemo-bloque-b-ia-design.md` (PR-B4) · **Rama:** `feat/mnemo-ai-repair` (desde `main` 7c159f1, con B1+B2+B3)

## Objetivo

Cuando el self-heal **determinista** no cura un fallo de mantenimiento (no es un locator roto: un `expect` desfasado, un `sleep` frágil, un dato de fixture obsoleto), proponer un **parche generado por LLM** que sí lo corrige — el "wow" de reparación sobre lo ya construido, sin romper el piso determinista ni la confianza (Nivel 2, humano aprueba, nunca firmado ni auto-merge).

## Decisiones (confirmadas)

- **Parche APLICADO leyendo el test:** Mnemo lee el código del test del repo, el LLM propone el bloque corregido viendo el error + el código, y se abre un PR borrador con el cambio aplicado (no una mera sugerencia).
- **Mecanismo: el LLM genera el bloque, reusa `open_draft_pr`** (`content.replace(old_str, new_str, 1)`). Sin runner Node. ts-morph/AST = follow-up.
- **Validación: PR "no validado" + CI del cliente + humano.** Mnemo NO ejecuta el test (no tiene el entorno del cliente).
- **Reusa `kind="self_heal"`** (distinguido por `payload.ai_repair=True`) para no duplicar el routing/materialización.
- Determinista intacto; on-premise/híbrido (B1); `DATABASE_URL`=prod; main protegida; TDD por subagentes; commits con `Claude-Session`.

## Componentes

### 1. `CodeHost.read_file` (interfaz `src/actions/base.py` + `github_app` + `NullCodeHost`)
Nuevo método en el `Protocol CodeHost`: `read_file(self, file_path: str) -> Optional[str]`. `GitHubCodeHost` lo implementa reusando `_get_file(file_path, default_branch)` (devuelve solo el contenido, o `None` si no existe / error). `NullCodeHost.read_file` → `None` (sin GitHub → no hay reparación IA; degrada). Permite que el actuator vea el código del test.

### 2. `AIRepairActuator` (`src/actions/ai_repair.py`)
`AIRepairActuator(provider)` con `propose(verdict, context) -> Optional[ActionProposal]`:
- Requiere `context["test_source"]` (el código del test, leído por el service) y el error (`context["error_message"]`/trace) + `context["file"]`. Si falta `test_source` o `file` → `None` (degrada).
- Llama `generate_structured` (B1) con un prompt que recibe el código del test + el error y pide un JSON `{old_block, new_block, explanation, confidence, citations}` (el `old_block` debe ser una subcadena EXACTA del `test_source` para que `str.replace` aplique; el prompt lo exige).
- Valida: si `old_block` no está en `test_source`, o `old_block == new_block`, o `confidence` baja → `None` (no propone un parche no aplicable/inútil).
- Si OK → `ActionProposal(kind="self_heal", payload={"file": file, "broken_locator": old_block, "suggested_locator": new_block, "reasoning": explanation, "candidates": [], "ai_repair": True, "masking_risk": True}, summary=f"Reparación IA: {file}")`.
- Nunca lanza (try/except → None), como el `SelfHealActuator`.

### 3. Wiring del fallback (`src/actions/service.py`)
Para `maintenance`, el orden es: **determinista primero, IA si no cura.** Concretamente, en `propose_actions` (o un actuator compuesto `MaintenanceActuator([SelfHealActuator, AIRepairActuator])`):
1. Intentar el `SelfHealActuator` determinista (como hoy).
2. Si devuelve `None` (no es un locator curable) y hay `codehost_factory` configurado: leer el código del test (`codehost.read_file(file)`), añadirlo al contexto como `test_source`, e intentar el `AIRepairActuator`.
- La lectura del archivo solo ocurre cuando el determinista no curó (evita una llamada GitHub por cada fallo).
- Si no hay codehost (NullCodeHost / sin GitHub) → no hay `test_source` → `AIRepairActuator` degrada → no hay reparación IA (comportamiento actual intacto).

### 4. Materialización (`src/ci/github_app.py` `open_draft_pr` + `src/actions/service.py` `_self_heal_body`)
- `open_draft_pr` se reusa **sin cambios** (`old_str=old_block`, `new_str=new_block` → `content.replace`). Si el `old_block` ya no está en el archivo (cambió entre propose y materialize) → `None` → degrada (no PR).
- `_self_heal_body`: cuando `payload.ai_repair`, el cuerpo del PR dice "**Parche propuesto por IA — NO auto-validado.** Requiere que el CI y un revisor humano lo verifiquen", además de la advertencia `masking_risk` existente y el `reasoning`.

## Garantías

- **Determinismo intacto:** el parche IA es una propuesta Nivel 2; el veredicto firmado y el gate no se tocan.
- **Validación externa:** PR borrador "no validado"; el CI del cliente (al abrir el PR) + el humano validan. Mnemo no ejecuta.
- **Citas + judge:** la salida lleva `citations` → evaluable por el judge de B1.
- **Degradación e2e:** sin LLM, sin codehost, sin `test_source`, o parche no aplicable → `None`, el flujo sigue, nada rompe.
- **Híbrido/privacidad:** usa `get_llm_provider()` (Ollama local por defecto); el código del test va al prompt → con Ollama local no sale de la infra (coherente con `ALLOW_EXTERNAL_LLM`).

## Testing (TDD)

- **`CodeHost.read_file`:** unit del `GitHubCodeHost.read_file` (mock session → contenido / None); `NullCodeHost.read_file → None`.
- **`AIRepairActuator`:** unit con provider mock — propone old/new cuando el LLM da un `old_block` presente en `test_source`; degrada si `old_block` no está / sin `test_source` / sin LLM / `old==new`.
- **Wiring:** unit del fallback — un `maintenance` que el `SelfHealActuator` no cura → se intenta el `AIRepairActuator` con el `test_source` leído (codehost mock); si el determinista cura, NO se lee el archivo (no llamada extra).
- **`_self_heal_body`:** el cuerpo lleva la nota "parche IA no auto-validado" cuando `ai_repair`.
- Provider + codehost mockeados (sin LLM ni GitHub reales). `python3 -m pytest`.

## Fuera de alcance (follow-ups / otros)

- **ts-morph/AST** (precisión sobre Page Objects multi-fichero), validación por ejecución, parches multi-bloque.
- **B5** (agente orquestador) — integra B1-B4.
- UI / Bloque C (demo).
