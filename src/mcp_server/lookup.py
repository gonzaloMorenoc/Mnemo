"""«¿Qué sabe el equipo de este fallo?»: de lo que da un asistente (nombre del test,
mensaje de error…) a las familias de defectos de la organización.

Tres vías, de más a menos segura: la huella exacta (misma que la ingesta), el nombre
del test y, si hay mensaje, el parecido semántico. Con `project`, solo familias con
fallos en ese proyecto. Las consultas van SIEMPRE acotadas a la org del token.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from psycopg.rows import dict_row

from src.defects.fingerprint import fingerprint
from src.ingest.models import FailureRecord

MAX_FAMILIES = 3

_Q_BY_FINGERPRINT = """
    select fl.defect_family_id::text as family_id, max(fl.created_at) as seen
    from public.failures fl
    join public.test_runs r on r.id = fl.run_id
    where fl.org_id = %(org)s and fl.fingerprint = %(fp)s and fl.defect_family_id is not null
      and (%(proj)s::text is null or r.project = %(proj)s)
    group by fl.defect_family_id
    order by seen desc
    limit %(limit)s
"""

# Nombre exacto (sin mayúsculas) primero; si no, el nombre que lo contiene.
_Q_BY_TEST_NAME = """
    select fl.defect_family_id::text as family_id,
           bool_or(lower(fl.test_name) = lower(%(name)s)) as exact,
           max(fl.created_at) as seen
    from public.failures fl
    join public.test_runs r on r.id = fl.run_id
    where fl.org_id = %(org)s and fl.defect_family_id is not null
      and (lower(fl.test_name) = lower(%(name)s)
           or (%(pattern)s::text is not null
               and lower(fl.test_name) like '%%' || %(pattern)s || '%%' escape '\\'))
      and (%(proj)s::text is null or r.project = %(proj)s)
    group by fl.defect_family_id
    order by exact desc, seen desc
    limit %(limit)s
"""


# Familias que TAMBIÉN fallan en otro proyecto: su texto (razón, autor, título, causa)
# puede venir de ese otro proyecto — triage_corrections no guarda el proyecto.
_Q_SHARED = """
    select distinct fl.defect_family_id::text as family_id
    from public.failures fl
    join public.test_runs r on r.id = fl.run_id
    where fl.org_id = %(org)s and fl.defect_family_id = any(%(ids)s::uuid[])
      and r.project is distinct from %(proj)s
"""

_Q_KINDS = """
    select id::text as id, kind from public.qa_knowledge
    where org_id = %(org)s and id = any(%(ids)s::uuid[])
"""

MIN_SUBSTRING = 3   # por debajo, solo nombre exacto (un «%a%» recorre todos los fallos)


def _like_escape(text: str) -> str:
    return text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _default_connection():
    from src.db.pool import get_pool
    return get_pool().connection()


class FailureLookup:
    def __init__(self, connection_factory: Callable = _default_connection):
        self._connect = connection_factory

    def find(self, *, org_id: str, test_name: str, message: str = "",
             error_type: Optional[str] = None, file: Optional[str] = None,
             trace: Optional[str] = None, project: Optional[str] = None) -> List[dict]:
        """[{family_id, match}] sin repetir, como mucho MAX_FAMILIES; match ∈
        {"huella", "nombre_exacto", "nombre"}. El parecido semántico lo añade quien llama."""
        found: List[dict] = []
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            if message.strip():
                rec = FailureRecord(test_name=test_name, error_type=error_type, message=message,
                                    trace=trace, project=project or "", source="mcp", file=file)
                cur.execute(_Q_BY_FINGERPRINT, {"org": org_id, "fp": fingerprint(rec),
                                                "proj": project, "limit": MAX_FAMILIES})
                found += [{"family_id": r["family_id"], "match": "huella"} for r in cur.fetchall()]
            name = test_name.strip()
            if name:
                pattern = _like_escape(name) if len(name) >= MIN_SUBSTRING else None
                cur.execute(_Q_BY_TEST_NAME, {"org": org_id, "name": name,
                                              "pattern": pattern,
                                              "proj": project, "limit": MAX_FAMILIES})
                found += [{"family_id": r["family_id"],
                           "match": "nombre_exacto" if r["exact"] else "nombre"}
                          for r in cur.fetchall()]
        return dedupe(found)

    def shared_with_other_projects(self, *, org_id: str, family_ids: List[str],
                                   project: str) -> set:
        """Familias (de las dadas) con fallos también en OTRO proyecto de la org."""
        if not family_ids:
            return set()
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_Q_SHARED, {"org": org_id, "ids": list(family_ids), "proj": project})
            return {r["family_id"] for r in cur.fetchall()}

    def knowledge_kinds(self, *, org_id: str, ids: List[str]) -> dict:
        """{id: kind} de elementos de conocimiento de la org."""
        if not ids:
            return {}
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_Q_KINDS, {"org": org_id, "ids": list(ids)})
            return {r["id"]: r["kind"] for r in cur.fetchall()}


def dedupe(found: List[dict]) -> List[dict]:
    seen, out = set(), []
    for item in found:
        if item["family_id"] not in seen:
            seen.add(item["family_id"])
            out.append(item)
    return out[:MAX_FAMILIES]
