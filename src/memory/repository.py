"""Carga `FamilyMemory` en lote: un número fijo de consultas para N familias (sin N+1).

La pertenencia a la organización se comprueba aquí, como en el resto de repositorios:
el pooler hace bypass de RLS. Las familias se limitan a las de la propia org
(scope='org'): nunca se mezcla memoria de otra organización.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from psycopg.rows import dict_row

from src.memory.family_memory import LESSON_KINDS, MAX_LESSONS, MAX_LOAD, FamilyMemory, Lesson
from src.sanitizer import sanitize_for_llm

logger = logging.getLogger(__name__)

_Q_MEMBER = ("select exists (select 1 from public.memberships"
             " where org_id = %(org)s and user_id = %(user)s) as ok")

# Última corrección CON razón que respalda la etiqueta VIGENTE: si María etiquetó
# «flaky» con razón y luego Pablo «real» sin razón, citar a María junto a «real»
# contradiría lo mostrado. El autor sale fuera por su nombre visible; el email solo
# va a la app (miembros), nunca a GitHub ni al CI.
_Q_FAMILIES = """
    select f.id::text as family_id, f.title, f.label, f.first_seen, f.last_seen,
           c.reason, c.corrected_at, p.display_name as reason_by, u.email as reason_by_email,
           (c.corrected_by is null or exists (
                select 1 from public.memberships m
                where m.org_id = f.org_id and m.user_id = c.corrected_by)) as reason_by_active
    from public.defect_families f
    left join lateral (
        select tc.reason, tc.corrected_at, tc.corrected_by
        from public.triage_corrections tc
        where tc.family_id = f.id and tc.org_id = f.org_id
          and tc.human_category = f.label
          and coalesce(btrim(tc.reason), '') <> ''
        order by tc.corrected_at desc
        limit 1
    ) c on true
    left join public.profiles p on p.user_id = c.corrected_by
    left join auth.users u on u.id = c.corrected_by
    where f.org_id = %(org)s and f.scope = 'org' and f.id = any(%(ids)s::uuid[])
"""

_Q_LESSONS = """
    select family_id, id, kind, title, summary from (
        select k.defect_family_id::text as family_id, k.id::text as id, k.kind, k.title,
               coalesce(nullif(btrim(k.approach), ''), nullif(btrim(k.challenge), ''),
                        k.outcome) as summary,
               row_number() over (partition by k.defect_family_id
                                  order by k.created_at desc, k.id) as rn
        from public.qa_knowledge k
        where k.org_id = %(org)s and k.status = 'activo'
          and k.kind = any(%(kinds)s)
          and k.defect_family_id = any(%(ids)s::uuid[])
    ) ranked
    where rn <= %(max_lessons)s
    order by family_id, rn
"""

_Q_STATS = """
    select fl.defect_family_id::text as family_id,
           count(distinct fl.run_id) as runs,
           array_agg(distinct r.project order by r.project) as projects
    from public.failures fl
    join public.test_runs r on r.id = fl.run_id
    where fl.org_id = %(org)s and fl.defect_family_id = any(%(ids)s::uuid[])
    group by fl.defect_family_id
"""

# Familias de un run, primero las que más fallos aportan (orden total y estable).
_Q_RUN_FAMILIES = """
    select r.org_id::text as org_id, fl.defect_family_id::text as family_id, count(*) as n
    from public.test_runs r
    join public.failures fl on fl.run_id = r.id
    where r.id = %(run)s and fl.defect_family_id is not null
      and exists (select 1 from public.memberships m
                  where m.org_id = r.org_id and m.user_id = %(user)s)
    group by r.org_id, fl.defect_family_id
    order by n desc, family_id
"""


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _clean(text: Optional[str]) -> Optional[str]:
    """Saneado del punto de SALIDA (GitHub, logs del CI): credenciales, tokens y datos
    personales. No el de desidentificación de logs (`sanitize_text`), que toma
    «peticiones/minuto» por una ruta y destroza la razón que escribió una persona."""
    if not text or not text.strip():
        return None
    return sanitize_for_llm(text)


def _default_connection():
    from src.db.pool import get_pool
    return get_pool().connection()


class FamilyMemoryRepository:
    def __init__(self, connection_factory: Callable = _default_connection):
        self._connect = connection_factory

    def load(self, *, user_id: str, org_id: str,
             family_ids: Sequence[str]) -> List[FamilyMemory]:
        """Memoria de las familias pedidas, en el MISMO orden. [] si no es miembro."""
        ids = list(dict.fromkeys(str(f) for f in family_ids if f))[:MAX_LOAD]
        if not ids:
            return []
        params = {"org": org_id, "user": user_id, "ids": ids, "max_lessons": MAX_LESSONS,
                  "kinds": list(LESSON_KINDS)}
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_Q_MEMBER, params)
            if not cur.fetchone()["ok"]:
                return []
            cur.execute(_Q_FAMILIES, params)
            families = {r["family_id"]: r for r in cur.fetchall()}
            cur.execute(_Q_LESSONS, params)
            lessons: Dict[str, List[Lesson]] = {}
            for r in cur.fetchall():
                lessons.setdefault(r["family_id"], []).append(
                    Lesson(id=r["id"], kind=r["kind"], title=_clean(r["title"]) or "",
                           summary=_clean(r["summary"]) or ""))
            cur.execute(_Q_STATS, params)
            stats = {r["family_id"]: r for r in cur.fetchall()}
        return [self._build(families[fid], lessons.get(fid, []), stats.get(fid))
                for fid in ids if fid in families]

    @staticmethod
    def _build(row: Dict[str, Any], lessons: List[Lesson],
               stats: Optional[Dict[str, Any]]) -> FamilyMemory:
        return FamilyMemory(
            family_id=row["family_id"],
            title=_clean(row["title"]) or "(sin título)",
            label=row["label"],
            reason=_clean(row["reason"]),
            reason_by=row["reason_by"] if row["reason"] else None,
            reason_by_email=row["reason_by_email"] if row["reason"] else None,
            reason_by_active=bool(row["reason_by_active"]),
            reason_at=_iso(row["corrected_at"]),
            lessons=tuple(lessons),
            projects=tuple(p for p in (stats or {}).get("projects") or () if p),
            runs=int((stats or {}).get("runs") or 0),
            first_seen=_iso(row["first_seen"]),
            last_seen=_iso(row["last_seen"]),
        )

    def families_of_run(self, *, user_id: str, run_id: str) -> Tuple[Optional[str], List[str]]:
        """(org_id, familias del run por nº de fallos). (None, []) si no es miembro."""
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_Q_RUN_FAMILIES, {"run": run_id, "user": user_id})
            rows = cur.fetchall()
        if not rows:
            return None, []
        return rows[0]["org_id"], [r["family_id"] for r in rows]

    def for_run(self, *, user_id: str, run_id: str) -> List[FamilyMemory]:
        org_id, family_ids = self.families_of_run(user_id=user_id, run_id=run_id)
        if not org_id:
            return []
        return self.load(user_id=user_id, org_id=org_id, family_ids=family_ids)

    def org_of_family(self, family_id: str) -> Optional[str]:
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select org_id::text as org_id from public.defect_families"
                        " where id = %s and scope = 'org'", (family_id,))
            row = cur.fetchone()
        return row["org_id"] if row else None
