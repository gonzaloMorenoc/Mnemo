# Mnemo Autopilot — F2f: desempate LLM de los ambiguos (diseño)

**Fecha:** 2026-06-23 · **Fase:** F2f (última de F2) · **Rama:** `feat/mnemo-triage` (mismo PR de F2)

## Objetivo

Resolver los veredictos de triaje ambiguos (`status='needs_tiebreak'`, los que el motor determinista dejó en `unknown`) con el **LLM local**, de forma **explícita y fuera del camino crítico**: un endpoint `POST /v2/triage/run/{id}/resolve` dispara la resolución; el `GET /v2/triage/run/{id}` sigue siendo lectura pura y rápida.

## Desviación respecto al spec de F2

El spec de F2 (`2026-06-22-mnemo-autopilot-f2-triage-design.md`, §3.5/§7) decía que el `GET /v2/triage/run/{id}` resolvería los pendientes de forma **perezosa**. **Esto se reemplaza** por un endpoint **POST** explícito. Motivo: el LLM local (DeepSeek-R1 8B) es lento (1-3 min/llamada); un GET con efectos secundarios podría tardar minutos o dar timeout, y la bandeja de aprobación (F5) que consume el GET no debe bloquearse. El coste del LLM queda explícito y controlado por quien llama. El resto del tiebreaker (§3.3: confianza capada, `llm_assisted`, auditable) se mantiene.

## Componentes

### 1. `src/triage/tiebreaker.py` (lógica pura + adaptador LLM)

- **`Tiebreaker`** (Protocol): `resolve(evidence: dict) -> Optional[Tuple[str, str]]` — devuelve `(categoría, razón)` con `categoría ∈ {flaky, infra, maintenance, real}`, o `None` si no puede decidir.
- **`LLMTiebreaker`** (implementación): usa `get_llm_provider` de forma **perezosa** (igual que el narrator/root_cause). Construye un prompt desde el `evidence_bundle` del ambiguo (señales disparadas, error_type, regla) pidiendo **una** de las 4 categorías + una razón breve. Parsea la respuesta a una categoría válida (normaliza, busca la palabra clave); si el LLM falla/está ausente o la respuesta no contiene ninguna de las 4 categorías → devuelve **`None`** (degrada).
- **`parse_category(text) -> Optional[str]`**: helper puro que extrae la categoría de la respuesta del LLM (testeable sin LLM).

### 2. `TriageService.resolve_tiebreaks(user_id, run_id) -> Dict[str, int]`

- Carga los veredictos del run (reusa `repo.get_triage_for_run`), filtra `status == 'needs_tiebreak'`.
- Por cada uno: llama a `self.tiebreaker.resolve(evidence_bundle)`.
  - Si devuelve `(categoría, razón)` → actualiza el veredicto: `category=categoría`, `confidence=0.70`, `llm_assisted=True`, `requires_approval=True` (por `llm_assisted` — lo que decide el LLM **siempre** pasa por humano), `status='resolved'`, y enriquece el `evidence_bundle` con `{"llm_assisted": True, "tiebreak_reason": razón, "tiebreak_category": categoría}`. Persiste vía `repo.update_triage_verdict`.
  - Si `None` → lo deja `needs_tiebreak` (no se toca).
- Devuelve `{"resolved": n, "pending": m}`.
- El `tiebreaker` se **inyecta** en `TriageService.__init__` (default `LLMTiebreaker()`), de modo que el servicio es testeable con un tiebreaker mockeado (sin LLM).

### 3. Repo `AssuranceRepository.update_triage_verdict(...)`

`update_triage_verdict(*, user_id, verdict_id, category, confidence, requires_approval, llm_assisted, status, evidence_bundle) -> bool` — actualiza un veredicto por id, **membership-gated** (vía join al run/org del veredicto, igual patrón que el resto). Devuelve `False` si no es miembro / no existe. (La lectura reusa `get_triage_for_run` de F2d.)

### 4. Endpoint `POST /v2/triage/run/{id}/resolve`

- `Depends(get_current_user)` (401) + el singleton `get_triage_service`.
- Llama a `triage_service.resolve_tiebreaks(user_id=user.user_id, run_id=run_id)` y devuelve `{"resolved": n, "pending": m}`.
- Errores: 401 (sin auth), 502 (error de BD), 503 (multi-tenant no configurado). Que el LLM no esté disponible **no es error** (deja pendientes → `pending` > 0). 
- El `GET /v2/triage/run/{id}` **no cambia** (lectura pura de los veredictos persistidos).

## Flujo de datos

```
POST /v2/triage/run/{id}/resolve
  → TriageService.resolve_tiebreaks
      → get_triage_for_run(run)                    [F2d, reusa]
      → filtra status=='needs_tiebreak'
      → por cada uno: tiebreaker.resolve(evidence) → (cat, razón) | None
            (cat) → update_triage_verdict(0.70, llm_assisted, requires_approval, resolved)
            None  → se queda needs_tiebreak
      → {resolved, pending}
```

## Manejo de errores / degradación

- **LLM ausente o lento que falla:** `LLMTiebreaker.resolve` captura la excepción y devuelve `None`; el ambiguo se queda `needs_tiebreak` (se puede reintentar con otro POST). Nunca rompe el endpoint.
- **Respuesta del LLM no parseable:** `parse_category` → `None` → se queda pendiente.
- **Error de BD** (en `get_triage_for_run`/`update_triage_verdict`): 502.
- **Auditabilidad:** la razón del LLM y `llm_assisted=True` quedan en el `evidence_bundle` (lo que firmará el certificado en F4 distingue lo determinista de lo asistido por LLM).

## Testing

- **`tiebreaker`** (sin LLM): `parse_category` con respuestas válidas (cada categoría) / basura → `None`; `LLMTiebreaker.resolve` con un provider mockeado (respuesta válida → `(cat, razón)`; provider lanza excepción → `None`).
- **`resolve_tiebreaks`** (repo + tiebreaker mockeados): solo los `needs_tiebreak` se resuelven; el resuelto se persiste con `0.70`/`llm_assisted=True`/`requires_approval=True`/`status='resolved'` y `tiebreak_reason` en el bundle; `None` → sigue pendiente (no se llama `update_triage_verdict`); cuenta `{resolved, pending}` correcta.
- **Endpoint** (servicio mockeado): POST devuelve el summary; 401 sin auth; 502 en error de BD.
- **`update_triage_verdict`** (integration): actualiza un veredicto y `get_triage_for_run` lo refleja; no-miembro → `False`.

## Fases (tareas del plan)

1. `tiebreaker.py` (`parse_category` puro + `LLMTiebreaker` con provider perezoso) + tests.
2. `repo.update_triage_verdict` + tests integration.
3. `TriageService.resolve_tiebreaks` (tiebreaker inyectado) + tests con mocks.
4. Endpoint `POST /v2/triage/run/{id}/resolve` + wiring + tests.

## Fuera de alcance (YAGNI)

- Reintento automático / cola de tiebreaks (un POST manual basta; F5 lo orquestará desde la UI).
- Aprendizaje del tiebreak (eso es el lazo de F5 vía `set_family_label`).
- Streaming de la respuesta del LLM.
