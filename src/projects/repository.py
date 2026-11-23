"""Acceso a `public.projects`. La pertenencia se comprueba aquí (el pooler hace bypass
de RLS); el ROL lo exige la API con `enforce`.

La clave (`key`) es el texto que usan las 5 tablas y el acta firmada: nunca se
modifica. Se edita el nombre visible, la descripción y el archivado.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

_COLUMNS = """
    p.id::text as id, p.key, p.name, p.description, p.is_example,
    p.archived_at is not null as archived, p.created_at,
    (select count(*) from public.test_runs r
      where r.org_id = p.org_id and r.project = p.key) as runs,
    (select max(r.created_at) from public.test_runs r
      where r.org_id = p.org_id and r.project = p.key) as last_run_at,
    (select count(*) from public.qa_knowledge k
      where k.org_id = p.org_id and k.project = p.key and k.status = 'activo') as knowledge
"""


class ProjectExists(Exception):
    """Ya hay un proyecto con esa clave en la organización."""


def _default_connection():
    from src.db.pool import get_pool
    return get_pool().connection()


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row(r: Dict[str, Any]) -> Dict[str, Any]:
    return {**r, "created_at": _iso(r["created_at"]), "last_run_at": _iso(r.get("last_run_at")),
            "runs": int(r.get("runs") or 0), "knowledge": int(r.get("knowledge") or 0)}


class ProjectRepository:
    def __init__(self, connection_factory: Callable = _default_connection):
        self._connect = connection_factory

    def list(self, *, user_id: str, org_id: str,
             include_archived: bool = True) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"""
                select {_COLUMNS}
                from public.projects p
                where p.org_id = %(org)s
                  and (%(archived)s or p.archived_at is null)
                  and exists (select 1 from public.memberships m
                              where m.org_id = p.org_id and m.user_id = %(user)s)
                order by p.archived_at is not null, lower(p.name), p.key
            """, {"org": org_id, "user": user_id, "archived": include_archived})
            return [_row(r) for r in cur.fetchall()]

    def create(self, *, org_id: str, key: str, name: str,
               description: Optional[str]) -> Dict[str, Any]:
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute("insert into public.projects (org_id, key, name, description)"
                            " values (%s, %s, %s, %s) returning id::text as id",
                            (org_id, key, name, description))
            except psycopg.errors.UniqueViolation as exc:
                raise ProjectExists(key) from exc
            project_id = cur.fetchone()["id"]
            conn.commit()
        return self.get(project_id)

    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"select {_COLUMNS} from public.projects p where p.id = %s", (project_id,))
            row = cur.fetchone()
        return _row(row) if row else None

    def update(self, *, project_id: str, name: Optional[str] = None,
               description: Optional[str] = None,
               archived: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        """Solo nombre visible, descripción y archivado. None si no existe."""
        sets, params = [], []
        if name is not None:
            sets.append("name = %s")
            params.append(name)
        if description is not None:
            sets.append("description = %s")
            params.append(description or None)
        if archived is not None:
            sets.append("archived_at = case when %s then coalesce(archived_at, now()) end")
            params.append(archived)
        if not sets:
            return self.get(project_id)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"update public.projects set {', '.join(sets)} where id = %s",
                        (*params, project_id))
            updated = cur.rowcount
            conn.commit()
        return self.get(project_id) if updated else None
