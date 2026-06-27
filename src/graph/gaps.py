"""
detect_gaps — Detector determinista de huecos de conocimiento de QA.

Tres tipos de huecos:
  - defecto_sin_conocimiento: familias de defecto sin qa_knowledge que las referencie.
  - dominio_sin_leccion: dominios con knowledge vinculado a defectos pero sin lección.
  - riesgo_sin_mitigacion: knowledge de tipo riesgo/regla_negocio en dominio sin lección/patrón.

La detección es 100% SQL (determinista). El LLM sólo redacta la recommendation;
si falla, se usa un texto fijo. La función nunca lanza excepciones.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from src.ai.generate import generate_structured
from src.config import DATABASE_URL

# ---------------------------------------------------------------------------
# Fixed fallback recommendations per gap kind
# ---------------------------------------------------------------------------

_FALLBACK_REC: Dict[str, str] = {
    "defecto_sin_conocimiento": (
        "Captura una lección o patrón en qa_knowledge para documentar"
        " las causas y soluciones de este defecto recurrente."
    ),
    "dominio_sin_leccion": (
        "Añade al menos una lección (kind='leccion') para este dominio"
        " de forma que el equipo pueda aprender de los defectos conocidos."
    ),
    "riesgo_sin_mitigacion": (
        "Crea un patrón o lección (kind='leccion' o 'patron') para mitigar"
        " este riesgo o regla de negocio en el dominio correspondiente."
    ),
}

# ---------------------------------------------------------------------------
# Connection helpers — same pattern as GraphService / QaKnowledgeRepository
# ---------------------------------------------------------------------------


def _connect(db_url: str = DATABASE_URL):
    return psycopg.connect(db_url, row_factory=dict_row)


def _is_member(cur, org_id: str, user_id: str) -> bool:
    cur.execute(
        "select exists(select 1 from public.memberships"
        " where org_id=%s and user_id=%s) as ok",
        (org_id, user_id),
    )
    return bool(cur.fetchone()["ok"])


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------


def _severity_by_count(count: int) -> str:
    if count >= 5:
        return "alta"
    if count >= 2:
        return "media"
    return "baja"


# ---------------------------------------------------------------------------
# Recommendation helper — tries LLM, falls back to fixed text silently
# ---------------------------------------------------------------------------


def _recommendation(kind: str, title: str, provider=None) -> str:
    prompt = (
        f"Generate a concise, actionable QA recommendation (1-2 sentences) "
        f"for a coverage gap of type '{kind}' affecting: {title}."
    )
    try:
        result = generate_structured(
            prompt=prompt,
            context=[{"id": kind, "content": title}],
            schema={"recommendation": ""},
            provider=provider,
            on_failure="none",
        )
        if result and result.get("recommendation"):
            return result["recommendation"]
    except Exception:  # noqa: BLE001 — LLM failure → use fallback
        pass
    return _FALLBACK_REC[kind]


# ---------------------------------------------------------------------------
# SQL queries for the three gap kinds
# ---------------------------------------------------------------------------

_SQL_DEFECTO_SIN_CONOCIMIENTO = """
    select f.id, f.title, f.occurrence_count
    from public.defect_families f
    where f.org_id = %s
      and not exists (
          select 1 from public.qa_knowledge k
          where k.org_id = %s and k.defect_family_id = f.id
      )
"""

_SQL_DOMINIO_SIN_LECCION = """
    select k.domain
    from public.qa_knowledge k
    where k.org_id = %s
      and k.defect_family_id is not null
    group by k.domain
    having not bool_or(k.kind = 'leccion')
"""

_SQL_RIESGO_SIN_MITIGACION = """
    select k.id, k.title, k.kind, k.domain
    from public.qa_knowledge k
    where k.org_id = %s
      and k.kind in ('riesgo', 'regla_negocio')
      and not exists (
          select 1 from public.qa_knowledge m
          where m.org_id = %s
            and m.domain = k.domain
            and m.kind in ('leccion', 'patron')
      )
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_gaps(
    *,
    user_id: str,
    org_id: str,
    provider=None,
    db_url: str = DATABASE_URL,
) -> List[Dict[str, Any]]:
    """
    Detect knowledge coverage gaps for org_id, gated by user membership.

    Returns [] for non-members or on any error.
    Never raises.
    """
    try:
        return _detect_gaps_inner(
            user_id=user_id,
            org_id=org_id,
            provider=provider,
            db_url=db_url,
        )
    except Exception:  # noqa: BLE001 — catch-all guarantees no raise
        return []


def _detect_gaps_inner(
    *,
    user_id: str,
    org_id: str,
    provider: Optional[Any],
    db_url: str,
) -> List[Dict[str, Any]]:
    with _connect(db_url) as conn, conn.cursor() as cur:
        if not _is_member(cur, org_id, user_id):
            return []

        # --- Gap 1: defecto_sin_conocimiento ---
        cur.execute(_SQL_DEFECTO_SIN_CONOCIMIENTO, (org_id, org_id))
        defect_rows = cur.fetchall()

        # --- Gap 2: dominio_sin_leccion ---
        cur.execute(_SQL_DOMINIO_SIN_LECCION, (org_id,))
        domain_rows = cur.fetchall()

        # --- Gap 3: riesgo_sin_mitigacion ---
        cur.execute(_SQL_RIESGO_SIN_MITIGACION, (org_id, org_id))
        riesgo_rows = cur.fetchall()

    gaps: List[Dict[str, Any]] = []

    for row in defect_rows:
        title = row["title"]
        count = row.get("occurrence_count") or 0
        gaps.append({
            "kind": "defecto_sin_conocimiento",
            "title": title,
            "severity": _severity_by_count(count),
            "affected": row.get("id", ""),
            "recommendation": _recommendation("defecto_sin_conocimiento", title, provider),
        })

    for row in domain_rows:
        domain = row["domain"] or "sin_dominio"
        gaps.append({
            "kind": "dominio_sin_leccion",
            "title": domain,
            "severity": "media",
            "affected": domain,
            "recommendation": _recommendation("dominio_sin_leccion", domain, provider),
        })

    for row in riesgo_rows:
        title = row["title"]
        gaps.append({
            "kind": "riesgo_sin_mitigacion",
            "title": title,
            "severity": "alta",
            "affected": row.get("domain") or "",
            "recommendation": _recommendation("riesgo_sin_mitigacion", title, provider),
        })

    return gaps
