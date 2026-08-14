"""Riqueza de Demo MTP: historia semanal + triaje + KB + assets. Incremental.

Los runs entran por el pipeline REAL (CiIngestionService): manifiestos, familias,
occurrence_count y dedup por run_uid los pone el producto, no este script. El
run_uid semanal determinista hace que re-ejecutar añada SOLO las semanas que
falten — la org llega viva a la demo re-ejecutando esto la semana anterior.

Termina recalculando el índice de continuidad de los 6 proyectos: si el arco
(checkout-suite=95, banca-movil=25) se movió, `arc_ok` sale False — la regla del
encargo, ejecutable.
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg

from src.ci.models import CiTestResult
from src.demo.riqueza_data import ASSETS, FAMILY_TRIAGE, KB_ITEMS, WEEKLY_PROFILE
from src.demo.seed import _trend_artifact
from src.demo.seed_knowledge import _find_family, _load_orgs

START = date(2026, 7, 23)  # el día siguiente al último run del seed original


def week_uids(project: str, *, start: date = START,
              until: Optional[date] = None) -> List[Tuple[str, date]]:
    """[(run_uid, fecha_del_run)] por semana ISO desde start hasta until (hoy si None).
    Determinista: mismo rango → mismos uids. El run se fecha el jueves de su semana
    (capado a `until` para no fechar en el futuro)."""
    until = until or date.today()
    out: List[Tuple[str, date]] = []
    d = start
    seen = set()
    while d <= until:
        year, week, _ = d.isocalendar()
        if (year, week) not in seen:
            seen.add((year, week))
            jueves = date.fromisocalendar(year, week, 4)
            out.append((f"riqueza-{project}-{year}-W{week:02d}", min(jueves, until)))
        d += timedelta(days=7)
    return out


def _firmas_existentes(cur, org_id: str, project: str, limit: int = 3) -> List[CiTestResult]:
    """Firmas de fallo REALES del proyecto (verbatim de la BD, ya sanitizadas):
    re-ingerirlas produce el mismo fingerprint → misma familia, cero huérfanas."""
    cur.execute(
        "select distinct fl.test_name, fl.error_type, fl.message, fl.trace"
        " from public.failures fl join public.test_runs tr on tr.id = fl.run_id"
        " where tr.org_id = %s and tr.project = %s and fl.error_type is not null"
        " order by fl.test_name limit %s", (org_id, project, limit))
    return [CiTestResult(test_name=r[0], status="fail", error_type=r[1],
                         message=r[2], trace=r[3]) for r in cur.fetchall()]


def _haystacks(cur, org_id: str, solo_unknown: bool) -> List[Dict[str, str]]:
    """Familias con su material de matching (título + tests + mensaje)."""
    cur.execute(
        "select df.id, concat_ws(' ', df.title,"
        "       string_agg(distinct fl.test_name, ' '), max(fl.message)) as haystack"
        " from public.defect_families df"
        " left join public.failures fl on fl.defect_family_id = df.id"
        " where df.org_id = %s" + (" and df.label = 'unknown'" if solo_unknown else "") +
        " group by df.id, df.title", (org_id,))
    return [{"id": str(r[0]), "haystack": r[1]} for r in cur.fetchall()]


def _runs_sin_acta(cur, org_id: str) -> List[Tuple[str, Any, bool]]:
    """[(run_id, created_at, ya_triado)] de los runs de la org sin certificado,
    en orden cronológico (el acta hereda la calibración del momento de emitirse)."""
    cur.execute(
        "select tr.id, tr.created_at,"
        " exists(select 1 from public.triage_verdicts tv where tv.run_id = tr.id)"
        " from public.test_runs tr"
        " where tr.org_id = %s"
        "   and not exists (select 1 from public.certificates c where c.run_id = tr.id)"
        " order by tr.created_at", (org_id,))
    return [(str(r[0]), r[1], r[2]) for r in cur.fetchall()]


def _certificar_runs(db_url: str, *, org_id: str, user_id: str, arepo,
                     private_key: Optional[str] = None,
                     public_key: Optional[str] = None) -> int:
    """Triaje del motor + acta firmada de cada run sin certificado: sin acta el
    dashboard muestra el run «sin veredicto aún». Solo tría los runs que el motor
    no vio (no pisa un triaje hecho en vivo) y, como en seed.py, el acta es
    best-effort: sin clave de firma la siembra sigue. Las claves son inyectables
    (tests); por defecto las de config — en prod deben ser las REALES o las actas
    no verificarán en /verify."""
    from src.certify.repository import CertificateRepository
    from src.certify.service import CertificateService
    from src.config import (LLM_MODEL, MNEMO_SIGNING_PRIVATE_KEY,
                            MNEMO_SIGNING_PUBLIC_KEY, MNEMO_VERSION)
    from src.triage.service import TriageService

    triage = TriageService(repo=arepo)
    cert = CertificateService(
        repo=arepo, cert_repo=CertificateRepository(db_url),
        private_key=private_key or MNEMO_SIGNING_PRIVATE_KEY,
        public_key=public_key or MNEMO_SIGNING_PUBLIC_KEY,
        mnemo_version=MNEMO_VERSION, model_version=LLM_MODEL or "unknown",
        llm_provider=None)
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        pendientes = _runs_sin_acta(cur, org_id)
    emitidas = 0
    for run_id, run_fecha, triado in pendientes:
        if not triado:
            triage.triage_run(user_id=user_id, run_id=run_id)
        try:
            # El acta se fecha el día del run: el histórico cuenta una historia coherente.
            cert.generate(user_id=user_id, run_id=run_id, created_at=run_fecha.isoformat())
            emitidas += 1
        except Exception:  # noqa: BLE001 — el acta es opcional (p. ej. sin clave de firma)
            pass
    return emitidas


def seed_riqueza(*, db_url: str, demo_user_id: str,
                 until: Optional[date] = None,
                 signing_private_key: Optional[str] = None,
                 signing_public_key: Optional[str] = None) -> Dict[str, Any]:
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        orgs = _load_orgs(cur, demo_user_id)
        if "Demo MTP" not in orgs:
            return {"skipped": True, "reason": "ejecuta seed_demo primero"}
        org = orgs["Demo MTP"]
        firmas = {p: _firmas_existentes(cur, org, p)
                  for p, prof in WEEKLY_PROFILE.items() if prof["fail_weeks"]}

    # Imports tardíos: el embedder carga torch y solo hace falta al sembrar.
    from src.ci.ingestion_service import CiIngestionService
    from src.defects.embedder import LocalEmbedder
    from src.defects.repository import AssuranceRepository
    from src.knowledge.repository import QaKnowledgeRepository
    from src.repo_ingest.repository import TestAssetRepository

    embedder = LocalEmbedder()
    arepo = AssuranceRepository(db_url)
    ingest = CiIngestionService(repo=arepo, embedder=embedder)

    # -- 1) Runs semanales -------------------------------------------------
    runs_creados = 0
    backdates: List[Tuple[str, date]] = []
    for project, prof in WEEKLY_PROFILE.items():
        uids = week_uids(project, until=until)
        for i, (uid, fecha) in enumerate(uids):
            _, week, _ = fecha.isocalendar()
            es_ultimo = i == len(uids) - 1
            # El último run de cada proyecto es SIEMPRE verde: un acta se emite sin
            # fricción sobre un run sin fallos (fallos sin triar no se certifican).
            con_fallos = (prof["fail_weeks"] and not es_ultimo
                          and week % prof["fail_weeks"] == 0 and firmas.get(project))
            fails = list(firmas[project][: 1 + week % 2]) if con_fallos else []
            n_pass = prof["n_pass"] + (week % 5) - 2  # varía el manifiesto
            art = _trend_artifact(org_id=org, project=project,
                                  commit=f"riq{week:02d}{project[:4]}",
                                  n_pass=n_pass, failures=fails)
            # n_pass YA es el cuerpo del manifiesto; solo falta la identidad semanal.
            art = art.model_copy(update={"run_uid": uid})
            res = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
            if not res.get("deduplicated"):
                runs_creados += 1
                backdates.append((res["run_id"], fecha))

    if backdates:  # fechar cada run en su semana (UPDATE posterior, patrón seed.py)
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            for run_id, fecha in backdates:
                cur.execute("update public.test_runs set created_at=%s where id=%s",
                            (datetime.combine(fecha, time(10, 30), tzinfo=timezone.utc),
                             run_id))
            conn.commit()

    # -- 2) Triaje de las unknown ------------------------------------------
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        unknown = _haystacks(cur, org, solo_unknown=True)
    triadas = 0
    for keywords, label, reason in FAMILY_TRIAGE:
        fam_id = _find_family(unknown, keywords)
        if fam_id:
            arepo.set_family_label(user_id=demo_user_id, family_id=fam_id,
                                   label=label, reason=reason)
            unknown = [f for f in unknown if f["id"] != fam_id]
            triadas += 1

    # -- 3) Conocimiento ---------------------------------------------------
    krepo = QaKnowledgeRepository(db_url, embedder=embedder)
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute("select kind, title from public.qa_knowledge where org_id=%s", (org,))
        existentes = {(k, t) for k, t in cur.fetchall()}
        familias = _haystacks(cur, org, solo_unknown=False)
    kb_creados = 0
    for item in KB_ITEMS:
        if (item["kind"], item["title"]) in existentes:
            continue
        fam = _find_family(familias, item.get("family_keywords") or ())
        if krepo.create_item(
                user_id=demo_user_id, org_id=org, kind=item["kind"], title=item["title"],
                challenge=item.get("challenge"), approach=item.get("approach"),
                outcome=item.get("outcome"), domain=item.get("domain"),
                tags=item.get("tags"), project=item["project"],
                source="manual", confidence="confirmado",
                defect_family_id=fam) is not None:
            kb_creados += 1

    # -- 4) Assets (repo propio: no pisa los del seed original) ------------
    assets_repo = TestAssetRepository(db_url, embedder=embedder)
    assets_n = assets_repo.replace_for_repo(
        user_id=demo_user_id, org_id=org, repo="demo/riqueza",
        assets=[{"path": a["path"], "framework": a["framework"],
                 "domain": a["domain"], "content": a["content"]} for a in ASSETS])

    # -- 5) Actas: cada run sin certificado gana su veredicto firmado ------
    # Va tras el triaje de familias: el acta lee la calibración al emitirse.
    actas = _certificar_runs(db_url, org_id=org, user_id=demo_user_id, arepo=arepo,
                             private_key=signing_private_key,
                             public_key=signing_public_key)

    # -- 6) Verificación integrada: la regla del arco, ejecutable ----------
    from src.continuity.index import compute_index
    indices: Dict[str, Optional[int]] = {}
    for p in WEEKLY_PROFILE:
        idx = compute_index(user_id=demo_user_id, org_id=org, project=p)
        indices[p] = idx["score"] if idx else None
    arc_ok = indices.get("checkout-suite") == 95 and indices.get("banca-movil") == 25
    return {"runs_creados": runs_creados, "triadas": triadas, "kb_creados": kb_creados,
            "assets": assets_n, "actas": actas, "indices": indices, "arc_ok": arc_ok}
