"""Siembra de la demo de Mnemo: 2 orgs + 4 escenarios pre-procesados + baseline verde de test_perfil.

Produce:
  - Org A "Demo MTP"   → flaky + maintenance (green→red) + real + baseline verde de test_perfil,
                         todos triados + certificados
  - Org B "Cliente Beta" → run real propio (aislamiento)
  - fresh_push.json    → NO ingerido (munición del Acto 1 en vivo)

Idempotente: si Org A ya existe para este demo_user_id devuelve {"skipped": True}.
"""

import json
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import psycopg

from src.certify.repository import CertificateRepository
from src.certify.service import CertificateService
from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact, CiTestResult
from src.config import LLM_MODEL, MNEMO_SIGNING_PRIVATE_KEY, MNEMO_SIGNING_PUBLIC_KEY, MNEMO_VERSION
from src.defects.repository import AssuranceRepository
from src.demo.demo_catalog import BASELINE_DOM, FAILURE_CATALOG, RUN_CALENDAR, RunSpec
from src.demo.labeling import etiqueta_humana
from src.triage.service import TriageService

_FIX = pathlib.Path(__file__).parent.parent.parent / "scripts" / "demo_fixtures"

_PAD_TOTAL = 40  # tamaño plausible de una suite; los runs se rellenan hasta aquí con tests que pasan


def _padded(art: CiRunArtifact, total: int = _PAD_TOTAL) -> CiRunArtifact:
    """Rellena la suite con tests que pasan hasta `total`, para un manifiesto con cuerpo.
    No toca los tests existentes (los fallos que dirigen el triaje se conservan primero)."""
    have = len(art.tests)
    if have >= total:
        return art
    pad = [CiTestResult(test_name=f"test_suite_case_{i:03d}", status="pass") for i in range(total - have)]
    return art.model_copy(update={"tests": [*art.tests, *pad]})


def _trend_artifact(*, org_id: str, project: str, commit: str, n_pass: int,
                    failures: "list[CiTestResult] | None" = None) -> CiRunArtifact:
    """Un run de tendencia: n_pass tests que pasan + fallos opcionales (firmas conocidas)."""
    tests = [CiTestResult(test_name=f"test_suite_case_{i:03d}", status="pass") for i in range(n_pass)]
    tests.extend(failures or [])
    return CiRunArtifact(project=project, org_id=org_id, commit_sha=commit, source="playwright", tests=tests)


# Firmas de fallo conocidas: reproducen EXACTAMENTE el fingerprint (error_type +
# message normalizado + top_frame del trace — ver src/defects/fingerprint.py, NO
# el test_name) de un fallo de los fixtures nucleo, para que MERGEN en la misma
# familia que etiqueta seed_knowledge en vez de abrir familias nuevas sin etiquetar.
_FAIL_EXPORT = CiTestResult(test_name="test_export_csv", status="fail", error_type="AssertionError",
                            message="expected status 200 but got 500",
                            trace="at ExportService.export (export.ts:88)",
                            file="tests/export.spec.ts", line=88)  # == real.json
# Lección aprendida y hoy protegida por test: un TimeoutError genérico ("Timeout
# 30000ms waiting for #cart") NO casa ningún patrón de src/triage/patterns.py, así
# que el motor lo deja sin clasificar y ensucia el Defect DNA. Por eso todo fallo
# del catálogo pasa por test_todos_los_fallos_son_clasificables_por_el_motor.
_FAIL_LOGIN = CiTestResult(test_name="test_login", status="fail", error_type="NoSuchElementError",
                           message="locator not found: #submit",
                           file="tests/login.spec.ts", line=10,
                           # el DOM (no forma parte del fingerprint) reproduce el mismo cambio de
                           # selector que maintenance_red.json → la regla determinista R3 (locator +
                           # DOM distinto del ultimo verde) categoriza "maintenance" tambien aqui,
                           # sin depender de la calibracion de seed_knowledge.
                           dom="<form id=\"login\"><input name=\"user\"/><button id=\"send\">Entrar</button></form>"
                           )  # == maintenance_red.json


def _load_artifact(name: str, org_id: str) -> CiRunArtifact:
    data = json.loads((_FIX / name).read_text())
    data["org_id"] = org_id
    return CiRunArtifact.model_validate(data)


def _backdate_runs(db_url: str, programados: "list[tuple[str, float]]") -> None:
    """Coloca cada run en su fecha (días hacia atrás desde hoy).

    Es un UPDATE POSTERIOR a toda la ingesta: no altera el orden en que se
    procesaron los runs y, por tanto, tampoco el triaje ni el histórico que
    usan las reglas deterministas."""
    now = datetime.now(timezone.utc)
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        for run_id, days_ago in programados:
            cur.execute("update public.test_runs set created_at = %s where id = %s",
                        (now - timedelta(days=days_ago), run_id))
        conn.commit()


def _backdate_corrections(db_url: str, org_id: str, desde_dias: int = 75) -> None:
    """Reparte las correcciones sobre el histórico: un equipo etiqueta según van
    apareciendo los fallos, no todas el mismo día."""
    now = datetime.now(timezone.utc)
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute("select id from public.triage_corrections where org_id=%s"
                    " order by corrected_at", (org_id,))
        ids = [r[0] for r in cur.fetchall()]
        n = len(ids)
        for i, cid in enumerate(ids):
            days_ago = desde_dias - (i * desde_dias / max(1, n - 1))
            cur.execute("update public.triage_corrections set corrected_at=%s where id=%s",
                        (now - timedelta(days=days_ago), cid))
        conn.commit()


def _sembrar_run(spec: RunSpec, *, org_id: str, user_id: str, ingest, triage, cert) -> str:
    """Ingesta + triaje + acta de un run del calendario.

    El acta es best-effort: sin clave de firma configurada el resto de la demo
    debe seguir sembrándose igual."""
    fallos = [f for f in FAILURE_CATALOG[spec.project] if f.test_name in spec.failure_keys]
    # Los `green_keys` son tests que en este run PASAN, con el DOM que tenían
    # entonces: son el "antes" que la regla R3 compara para poder afirmar que un
    # localizador se rompió. Sin ese pasado, el motor no clasifica el fallo.
    verdes = [CiTestResult(test_name=k, status="pass", dom=BASELINE_DOM.get(k))
              for k in spec.green_keys]
    art = _trend_artifact(org_id=org_id, project=spec.project, commit=spec.commit,
                          n_pass=spec.n_pass, failures=[*verdes, *fallos])
    run_id = ingest.ingest_artifact(user_id=user_id, artifact=art)["run_id"]
    triage.triage_run(user_id=user_id, run_id=run_id)
    try:
        cert.generate(user_id=user_id, run_id=run_id,
                      created_at=datetime.now(timezone.utc).isoformat())
    except Exception:  # noqa: BLE001 — el acta es opcional (p. ej. sin clave de firma)
        pass
    return run_id


def _etiquetar_familias(db_url: str, *, org_id: str, user_id: str, repo,
                        solo_sin_etiquetar: bool = False) -> int:
    """Etiqueta las familias de la org; devuelve cuántas correcciones creó.

    Usa `set_family_label`, el MISMO camino que recorre un humano en la app:
    actualiza la familia y registra la corrección motor-vs-humano. Así la
    calibración de la demo se gana igual que la de un cliente real, en vez de
    escribirse a mano en la tabla.

    `solo_sin_etiquetar` es para la pasada final: recoge las familias que hayan
    nacido después (sin volver a corregir las ya revisadas, que duplicaría
    correcciones y falsearía la precisión)."""
    # Se lee la categoría que puso EL MOTOR en el último veredicto de la familia,
    # no `defect_families.label` (que vale 'unknown' hasta que alguien etiqueta).
    # Es la misma que compara `set_family_label` al registrar la corrección: si se
    # tomara la otra, todas las familias acabarían con la misma etiqueta y la
    # precisión se desplomaría por debajo del umbral de confianza.
    filtro = " and f.label = 'unknown'" if solo_sin_etiquetar else ""
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "select f.id,"
            " (select tv.category from public.triage_verdicts tv"
            "  join public.failures fa on fa.id = tv.failure_id"
            "  where fa.defect_family_id = f.id order by tv.created_at desc limit 1)"
            " from public.defect_families f"
            f" where f.org_id = %s{filtro} order by f.first_seen", (org_id,))
        familias = cur.fetchall()
    hechas = 0
    for i, (family_id, engine_label) in enumerate(familias):
        etiqueta = etiqueta_humana(engine_label or "unknown", i)
        if repo.set_family_label(user_id=user_id, family_id=str(family_id),
                                 label=etiqueta, reason="Revisión del equipo de QA"):
            hechas += 1
    return hechas


def _proponer_acciones(db_url: str, *, user_id: str, run_ids: "list[str]") -> int:
    """Propone acciones correctivas en los runs indicados para que el panel de
    Autopilot tenga contenido. Sin LLM: solo los actuadores deterministas
    (cuarentena de flaky y self-heal de locators). Best-effort."""
    from src.actions.quarantine import QuarantineActuator
    from src.actions.repository import ActionRepository
    from src.actions.selfheal.selfheal import SelfHealActuator
    from src.actions.service import ActionService
    from src.actions.ticket import TicketActuator

    # Sin LLM: el ticket de defecto real se propone igual (el análisis de causa
    # raíz degrada solo, ya está contemplado), el self-heal es determinista y la
    # cuarentena de flaky también. Es el mismo camino que usa la app.
    service = ActionService(
        repo=AssuranceRepository(db_url),
        actions_repo=ActionRepository(db_url),
        actuators={
            "flaky": QuarantineActuator(),
            "maintenance": SelfHealActuator(),
            "real": TicketActuator(None),
        },
    )
    propuestas = 0
    for run_id in run_ids:
        try:
            counts = service.propose_actions(user_id=user_id, run_id=run_id)
            propuestas += sum(v for k, v in counts.items() if k != "skipped")
        except Exception:  # noqa: BLE001 — el self-heal nunca tumba la siembra
            pass
    return propuestas


def _create_org(cur: Any, name: str, user_id: str) -> str:
    cur.execute(
        "insert into public.organizations (name, created_by) values (%s,%s) returning id",
        (name, user_id),
    )
    return str(cur.fetchone()[0])


def seed_demo(*, db_url: str, demo_user_id: str) -> Dict[str, Any]:
    """Siembra Org A (5 runs: flaky + maintenance green→red + real + baseline verde de test_perfil) + Org B (aislamiento). Idempotente.
    Devuelve un resumen con {org_a, org_b, runs, fresh_artifact_path}.
    Si Org A ya existe para este usuario devuelve {"skipped": True}.
    """
    # -- Idempotency check + org creation (atomic) ---------------------------
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id from public.organizations where created_by=%s and name=%s",
                (demo_user_id, "Demo MTP"),
            )
            if cur.fetchone():
                return {"skipped": True}
            org_a = _create_org(cur, "Demo MTP", demo_user_id)
            org_b = _create_org(cur, "Cliente Beta", demo_user_id)
        conn.commit()

    # -- Service construction (mirrors api_v2.get_*) -------------------------
    from src.defects.embedder import LocalEmbedder

    repo = AssuranceRepository(db_url)
    cert_repo = CertificateRepository(db_url)
    embedder = LocalEmbedder()

    ingest = CiIngestionService(repo=repo, embedder=embedder)
    triage = TriageService(repo=repo)

    llm = None  # sin ai_eval en el seed

    cert_svc = CertificateService(
        repo=repo,
        cert_repo=cert_repo,
        private_key=MNEMO_SIGNING_PRIVATE_KEY,
        public_key=MNEMO_SIGNING_PUBLIC_KEY,
        mnemo_version=MNEMO_VERSION,
        model_version=LLM_MODEL or "unknown",
        llm_provider=llm,
    )

    # -- Org A. El orden de las fases ES el diseño: la calibración se lee en el
    #    instante de emitir cada acta, así que sembrar en orden cronológico hace
    #    que el histórico MUESTRE al motor aprendiendo. Si las etiquetas fueran al
    #    final, ninguna acta saldría verde (era el comportamiento anterior).
    runs = []
    programados: list[tuple[str, float]] = []

    # Fase 0 — los 5 escenarios narrativos del guion (flaky, maintenance green→red,
    # real, baseline verde de test_perfil). Son la munición del Acto 1 en vivo.
    for i, name in enumerate(("maintenance_green.json", "maintenance_red.json", "flaky.json",
                              "real.json", "perfil_green.json")):
        art = _padded(_load_artifact(name, org_a))
        run_id = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)["run_id"]
        triage.triage_run(user_id=demo_user_id, run_id=run_id)
        try:
            cert_svc.generate(user_id=demo_user_id, run_id=run_id,
                              created_at=datetime.now(timezone.utc).isoformat())
        except Exception:  # noqa: BLE001 — cert opcional (p.ej. sin clave de firma)
            pass
        runs.append({"fixture": name, "run_id": run_id})
        programados.append((run_id, 90 - i * 0.5))  # justo antes del calendario

    # Fase 1 — histórico antiguo (>30 días). El motor AÚN NO conoce a este cliente:
    # estas actas nacen "apto-con-reservas" y eso es fiel, no un defecto.
    for spec in sorted((r for r in RUN_CALENDAR if r.days_ago > 30), key=lambda r: -r.days_ago):
        run_id = _sembrar_run(spec, org_id=org_a, user_id=demo_user_id,
                              ingest=ingest, triage=triage, cert=cert_svc)
        runs.append({"fixture": spec.commit, "run_id": run_id})
        programados.append((run_id, spec.days_ago))

    # Fase 2 — el trabajo humano. Etiquetar TODAS las familias abiertas hasta aquí
    # es lo que calibra el motor (>=30 correcciones) y lo que deja el Defect DNA
    # sin ruido. Va ANTES de las actas recientes: ese orden es lo que las hace verdes.
    correcciones = _etiquetar_familias(db_url, org_id=org_a, user_id=demo_user_id, repo=repo)

    # Fase 3 — histórico reciente. Con el motor ya calibrado, un run limpio con
    # manifiesto completo se firma "apto".
    recientes: list[str] = []
    for spec in sorted((r for r in RUN_CALENDAR if r.days_ago <= 30), key=lambda r: -r.days_ago):
        run_id = _sembrar_run(spec, org_id=org_a, user_id=demo_user_id,
                              ingest=ingest, triage=triage, cert=cert_svc)
        runs.append({"fixture": spec.commit, "run_id": run_id})
        programados.append((run_id, spec.days_ago))
        if spec.days_ago <= 30 and spec.failure_keys:
            recientes.append(run_id)

    # Fase 4 — repaso final: cualquier familia nacida en el tramo reciente se
    # etiqueta también. Una familia 'unknown' es ruido en el Defect DNA, y el
    # equipo de QA sigue revisando lo que va apareciendo.
    correcciones += _etiquetar_familias(db_url, org_id=org_a, user_id=demo_user_id,
                                        repo=repo, solo_sin_etiquetar=True)

    # Fase 5 — acciones correctivas sobre los últimos runs con fallos, para que el
    # panel de Autopilot no se vea vacío.
    acciones = _proponer_acciones(db_url, user_id=demo_user_id, run_ids=recientes)

    _backdate_runs(db_url, programados)
    _backdate_corrections(db_url, org_a)

    # -- Org B: un run real propio (aislamiento) -----------------------------
    for name in ("real.json",):
        art = _load_artifact(name, org_b)
        r = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        triage.triage_run(user_id=demo_user_id, run_id=r["run_id"])

    return {
        "org_a": org_a,
        "org_b": org_b,
        "runs": runs,
        "correcciones": correcciones,
        "acciones": acciones,
        "fresh_artifact_path": str(_FIX / "fresh_push.json"),
    }
