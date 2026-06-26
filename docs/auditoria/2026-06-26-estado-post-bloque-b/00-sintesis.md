# Auditoría de estado — post-Bloque B (síntesis)

**Fecha:** 2026-06-26 · **Tras:** Tanda 1 (hardening) + Bloque A (credibilidad) + Bloque B completo (B1–B5, IA protagonista), todo en `main` · **Concurso MTP:** quedan ~4 meses (deadline 30-oct-2026) · **Método:** 5 auditores opus en paralelo (vendibilidad, arquitectura, seguridad, tests, concurso) → informes en `01..05-*.md`.

## Veredicto global

**Motor sólido + IA honesta y bien factorizada, pero con tres frentes abiertos antes de poder DEMOSTRAR o VENDER.** El Bloque A suturó la credibilidad (el producto ya no miente: certificado = "acta de evidencia", `self_eval` real). El Bloque B es el mejor subsistema del repo (`src/ai/generate_structured` reusado sin duplicación, degradación honesta). Pero la auditoría destapa: (1) una **violación del invariante central** ("determinismo donde firmo") introducida sin querer en B1; (2) la **demo no arranca de extremo a extremo** (plumbing de última milla); (3) **endurecimiento pendiente** (authz de Nivel 2, exfiltración, RLS no testeada como comportamiento). Ninguno es un agujero de motor; todos son acotados y de bajo riesgo técnico. **No estamos listos para demostrar hoy, pero el camino es corto.**

## Scorecard por dimensión

| Dimensión | Nota | Estado |
|---|---|---|
| Credibilidad (Bloque A) | ✅ A− | Certificado reencuadrado + `self_eval` real. Herida "IA fantasma" suturada. |
| IA (Bloque B) | ✅ A− | 6 features sustanciales que degradan con honestidad; `src/ai/` ejemplar. **Pero** el judge toca el veredicto firmado (ver H1). |
| Arquitectura | 🟡 B+ | Motor limpio (DI, inmutabilidad, sin ciclos). **Pero** el entrypoint de prod es la app LEGACY sin auth + 2 God-objects que crecieron. |
| Seguridad/multitenancy | 🟡 Apto-piloto | 0 Críticos, 6 Altos. Aislamiento sin fisuras explotables; authz de Nivel 2 y exfiltración a cerrar. |
| Tests | 🟡 7/10 | Núcleo determinista testeado (hasta adversarial). **Pero** RLS no se prueba como comportamiento, cobertura no se mide, el "AI eval" de CI no evalúa IA. |
| Vendibilidad por millones | 🟡 CASI | Credibilidad cerrada; falta empaquetado Vía B (verificación pública del cert, entitlement) + cerrar 2 promesas (foso, patch). |
| Demo del concurso | 🔴 No lista | Motor+IA+frontend existen; falta la última milla (docker e2e, auto-gate, ROI, PDF). En camino de ganar. |

## Hallazgos transversales (cruzan ≥2 lentes — los más fuertes)

### H1 — 🔴 El LLM-judge contamina el veredicto FIRMADO (vendibilidad #1 + seguridad C-1)
En B1, `ai_eval` (faithfulness del LLM-judge) modula `confidence`, que modula el veredicto: `faithfulness<0.5 → confidence="low" → apto→apto-con-reservas` (`certify/certificate.py:38`). **Esto rompe "determinismo donde firmo" literalmente:** el veredicto firmado deja de ser función pura de señales deterministas y pasa a depender de un LLM no-determinista e inyectable. Peor: contradice el reencuadre del Bloque A — un certificado "de evidencia **reproducible**" cuyo veredicto un LLM puede mover en reruns **no es reproducible**. Es auto-inconsistencia introducida con buena intención (degradar es conservador) pero defectuosa.
- **Fix (barato, alto valor):** `ai_eval` se reporta DENTRO del `self_eval` (firmado como dato informativo), pero NO modula `confidence`/`verdict`. El veredicto vuelve a depender solo de señales deterministas (cold-start n<30, accuracy<0.60). Restaura el invariante Y la reproducibilidad. Mantiene la IA visible sin dejarla firmar.

### H2 — 🔴 La demo no corre de extremo a extremo (concurso #1 + arquitectura D-ARQ-1)
- La demo dockerizada **no arranca el motor**: `scripts/docker_init.py` aplica solo migraciones 001-006; faltan las de Autopilot (triaje/acciones/certificados/gate). `docker compose up` levanta un sistema sin el producto.
- El entrypoint de prod (`Dockerfile → uvicorn api:app`) es la **app LEGACY** (RAG v1, expone `/analyze,/sync,/history,/evaluate` **sin auth**); el Autopilot va colgado como router.
- "Push → gate rojo automático" (Acto 1) es **manual**: el `ci_webhook` ingesta+triaja pero no publica gate ni emite cert.
- **Fix:** `asgi.py` que monte solo `v2_router` + `CMD` del Dockerfile + migraciones completas en el init + cerrar el lazo webhook→gate→cert. Es el prerequisito de toda la demo.

### H3 — 🟠 El "AI eval" de CI no evalúa IA (vendibilidad + tests)
`scripts/eval_ai.py` (etiquetado "AI eval" en CI) ejecuta el motor **determinista** de triaje, sin LLM. El LLM-judge no tiene ni un test de corrección ("afirmación inventada → faithfulness<0.5"). El golden set son 10 casos. El eval real con RAGAS está marcado `@integration` y se salta en CI. → El `self_eval` que vendemos como auto-medición no tiene red en CI.

## Top issues priorizados

| # | Sev | Hallazgo | Lente | Fix | Coste |
|---|-----|----------|-------|-----|-------|
| H1 | 🔴 | LLM-judge mueve el veredicto firmado (rompe determinismo+reproducibilidad) | vend.+seg. | `ai_eval` informativo, no vinculante | Bajo |
| H2 | 🔴 | Demo no arranca e2e (migraciones docker + entrypoint legacy + webhook manual) | concurso+arq. | `asgi.py`+CMD+init+lazo webhook→gate→cert | Medio |
| A-1 | 🟠 | Aprobación de Nivel 2 (PR con código IA al repo del cliente) solo exige `is_org_member`, no admin | seg. | gate de rol admin en approve/materialize/reject | Bajo |
| T-RLS | 🟠 | RLS no se prueba como comportamiento (org-A no puede leer org-B a nivel de policy) | tests | test conductual cross-tenant (P0: es LA garantía) | Bajo |
| E-1 | 🟠 | `LANGCHAIN_TRACING_V2=true` envía prompts a LangSmith saltándose `ALLOW_EXTERNAL_LLM` | seg. | quitar de `.env.example`; gobernar bajo el flag | Bajo |
| E-2/I-1 | 🟠 | AIRepair manda el código del cliente entero sin truncar; salida LLM inyectable llega a escritura de PR | seg. | truncar+sanear; gobernar bajo el flag | Bajo |
| T-COV | 🟠 | Cobertura no medida (sin `pytest-cov --cov-fail-under`); el 80% es folklore | tests | instrumentar cobertura en CI | Bajo |
| S-3 | 🟡 | `AskRequest.question` sin cota de longitud (DoS+inyección) | seg. | `Field(max_length=...)` | Trivial |
| ARQ-2 | 🟡 | God-objects: `defects/repository.py` 988, `api_v2.py` 974 (>800) | arq. | partir por responsabilidad + `BaseRepository` | Medio |
| V-FOSO | 🟡 | El "foso" es tabla de etiquetas+dashboard; `tenant_accuracy` no realimenta decisiones | vend. | hacer que la calibración componga el triaje | Medio |
| V-VIAB | 🟡 | Vía B imposible: el cert no se puede verificar por un tercero (clave pública nunca publicada) | vend. | endpoint de verificación público + publicar la clave pública | Medio |

## Decisiones que requieren al usuario

1. **H1 (integridad del veredicto):** ¿corregimos ya que `ai_eval` deje de modular el veredicto firmado? (Recomiendo sí — es barato y de integridad; restaura la promesa central.)
2. **Base 11 / IP (riesgo de elegibilidad):** ¿la base del concurso cede a MTP los derechos de explotación? Si sí, la tesis "Vía B" (reventa del certificado) se tambalea y hay que replantear la narrativa de valoración del Bloque D. **Hay que leer la base 11 literal antes de construir el deck.** (No resoluble desde el repo.)
3. **Secuencia:** ¿un "Bloque B.5 de endurecimiento" (H1 + los 6 Altos + RLS conductual + cobertura) ANTES del Bloque C (demo)? ¿O demo primero y hardening en paralelo? (Recomiendo B.5 corto primero: H1+H2 son prerequisitos de una demo creíble.)

## Secuencia recomendada (~4 meses)

1. **Resolver la base 11** (IP) — desbloquea la narrativa del pitch; es lectura, no código.
2. **Bloque B.5 — endurecimiento (1-2 semanas):** H1 (veredicto determinista) + A-1 (authz Nivel 2) + E-1/E-2/I-1 (exfiltración) + S-3 + RLS conductual + cobertura en CI. Cierra integridad y seguridad antes de enseñar nada.
3. **H2 — arranque e2e (1-2 semanas):** `asgi.py`+CMD+migraciones completas + lazo webhook→gate→cert. Sin esto no hay demo.
4. **Bloque C — demo (3-4 semanas):** 3 actos e2e + seed de 3 escenarios + 2ª org (aislamiento) + ROI en pantalla + PDF del cert + ensayar ≥3× con plan B determinista.
5. **Bloque D — pitch (1-2 semanas):** % auto-triaje (medible, agregarlo) + coste 0€ (propiedad de diseño) + narrativa de valoración (condicionada a la base 11).
6. Colchón ~4-6 semanas.

**Lo que está sorprendentemente bien (preservar):** `src/ai/` (la mejor pieza); la firma Ed25519 verificada de verdad (tamper+round-trip); el árbol de triaje; la degradación elegante uniforme; la deuda de la auditoría previa (atomicidad, idempotencia, métrica del foso) ya pagada con las técnicas correctas. El equipo amortiza deuda — la excepción son los God-objects y el legacy en el arranque.
