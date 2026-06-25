# Mnemo Autopilot — F4b: Gate en CI (check run) (diseño)

**Fecha:** 2026-06-25 · **Fase:** F4b (segunda de F4, §7.1 del spec maestro) · **Rama:** `feat/mnemo-gate` (apilada sobre `feat/mnemo-certificate`/PR #20, que ya trae F3c + F4a; reapuntar a `main` cuando F4a mergee)

## Objetivo

Publicar, por run, un **check run `mnemo/assurance`** sobre el commit (`success`/`failure`/`neutral`) según el veredicto de aseguramiento, **reutilizando la política de F4a** (sin duplicarla). El "wow": un defecto real pone el PR en **rojo** (`failure`); al aprobar el self-heal y re-disparar el gate, pasa a **verde** (`success`). El check run es **saliente** (Mnemo→GitHub Checks API), disparado por un endpoint.

## Decisiones (confirmadas)

- **Disparador: endpoint explícito** `POST /v2/gate/run/{run_id}` (consistente con `/propose` y `/certificates`).
- **Reuso de la política:** extraer `compute_verdict(verdicts) -> str` de `build_certificate` (F4a) y que ambos la usen. **No duplicar.**
- **Mapeo veredicto → conclusion:** `no-apto → failure`, `apto-con-reservas → neutral`, `apto → success`.
- **No persistir** el resultado del gate (el check run vive en GitHub; sin tabla nueva, sin migración).
- **Reusa F3c/F4a:** `GitHubCodeHost` (+`publish_check_run`), `codehost_factory(org_id, user_id)`, `CertificateRepository.get_run_meta` (head_sha = `commit_sha`), `AssuranceRepository.get_triage_for_run`.

## Componentes

### `src/certify/certificate.py` — extraer `compute_verdict`
Extraer la lógica de veredicto actual (embebida en `build_certificate`) a una función pura:
```python
def compute_verdict(verdicts: List[Dict]) -> str:
    reales_novel_sin_approval = sum(1 for v in verdicts if v.get("category")=="real"
        and v.get("rule_applied")=="R5_real_novel" and not v.get("requires_approval"))
    pendientes_approval = sum(1 for v in verdicts if v.get("requires_approval"))
    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        return "no-apto"
    if any(v.get("category") in ("real", "maintenance") for v in verdicts):
        return "apto-con-reservas"
    return "apto"
```
`build_certificate` pasa a llamar `compute_verdict(verdicts)` para su campo `verdict` (mantiene el resto: breakdown, risk_score, evidencia). Los tests de `build_certificate` siguen verdes.

### `src/ci/github_app.py` — `GitHubCodeHost.publish_check_run`
```python
def publish_check_run(self, *, head_sha: str, conclusion: str, title: str, summary: str) -> str:
    resp = self._session.post(
        f"{_API}/repos/{self._repo}/check-runs",
        json={"name": "mnemo/assurance", "head_sha": head_sha, "status": "completed",
              "conclusion": conclusion, "output": {"title": title, "summary": summary}},
        headers=self._headers(), timeout=15)
    if resp.status_code >= 300:
        raise GitHubError(f"publish check-run falló: HTTP {resp.status_code}")
    return resp.json()["html_url"]
```
Requiere scope `checks:write` en la GitHub App (además de los de F3c).

### `src/certify/gate.py` — `GateService`
`GateService(*, repo, cert_repo, codehost_factory)` con:
```python
_CONCLUSION = {"no-apto": "failure", "apto-con-reservas": "neutral", "apto": "success"}

def publish(self, *, user_id, run_id) -> Dict:
    meta = self.cert_repo.get_run_meta(user_id=user_id, run_id=run_id)
    if meta is None:
        raise ValueError("run no encontrado o sin acceso")
    head_sha = meta.get("commit_sha")
    if not head_sha:
        raise ValueError("el run no tiene commit_sha; no se puede publicar el check run")
    verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
    if not verdicts:
        raise ValueError("run sin veredictos de triaje")
    verdict = compute_verdict(verdicts)
    conclusion = _CONCLUSION[verdict]
    title, summary = _render_output(verdict, verdicts)   # desglose + porqué
    codehost = self.codehost_factory(meta["org_id"], user_id)
    url = codehost.publish_check_run(head_sha=head_sha, conclusion=conclusion,
                                     title=title, summary=summary)
    return {"verdict": verdict, "conclusion": conclusion, "check_run_url": url}
```
`_render_output(verdict, verdicts)` arma un `title` (p. ej. `"Mnemo Assurance: no-apto"`) y un `summary` markdown con el desglose por categoría y el motivo (defecto real novedoso / pendientes de aprobación / todo curado). Puro.

### Endpoint (`api_v2`)
`POST /v2/gate/run/{run_id}` (`Depends(get_current_user)`) → `GateResponse {verdict, conclusion, check_run_url}`. `get_gate_service` (singleton) construye `GateService(repo=get_assurance_repo(), cert_repo=get_certificate_repo(), codehost_factory=_github_codehost_factory)`. F4b añade `get_certificate_repo()` (singleton sobre `_cert_repo`) y refactoriza `get_certificate_service` (F4a) para que lo use también — un único `CertificateRepository` compartido por ambos.

## Datos

Ninguno nuevo (no se persiste el gate). Sin migración.

## Manejo de errores

401 sin auth · run no encontrado / sin `commit_sha` / sin veredictos → **422** · org sin integración GitHub → **400** (`ValueError` del factory) · App no configurada → **503** (`GitHubAuthError`) · GitHub API → **502** (`GitHubError`) · BD → **502**. Aislamiento por-org en cada lectura (membership-gated); repo destino = el del org.

## Testing (TDD; `requests` mockeado)

- **`compute_verdict`** (puro): `no-apto` (real novedoso sin approval / pendiente), `apto-con-reservas` (real recurrente / maintenance), `apto` (flaky/infra). El refactor mantiene verdes los tests de `build_certificate`.
- **`publish_check_run`** (mock session): POST a `/check-runs` con `name="mnemo/assurance"`, `head_sha`, `conclusion`, `output`; devuelve la URL; `status>=300 → GitHubError`.
- **`GateService`** (mockeado): los 3 mapeos verdict→conclusion; `commit_sha` ausente → `ValueError`; sin veredictos → `ValueError`; `publish_check_run` invocado con el `head_sha` y la `conclusion` correctos.
- **Endpoint**: 200 (verdict/conclusion/url); 422 (sin commit/sin veredictos); 502 (GitHub/BD); 503 (App); 401 sin auth.

## Fases (tareas del plan)

1. Extraer `compute_verdict` en `certificate.py` (refactor; `build_certificate` lo usa) + test directo de `compute_verdict`.
2. `GitHubCodeHost.publish_check_run` + tests (`requests` mockeado).
3. `src/certify/gate.py` `GateService` (+ `_render_output`) + endpoint `POST /v2/gate/run/{id}` + `GateResponse` + wiring en `api_v2` + tests de service y endpoint.

## Fuera de alcance (YAGNI / fases posteriores)

- Disparo **automático** del gate (en el webhook CI, tras triaje) → roadmap (hoy: endpoint explícito).
- Persistir el histórico de gates / status `in_progress` antes del veredicto.
- **F5** (lazo de aprendizaje + frontend) · **F6** (demo).
