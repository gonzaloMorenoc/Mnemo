"""Ajuste de LLM externo por organización (migración 035, tabla org_llm_settings).

Sin fila para una org se aplica la política global (permitido): el interruptor solo
cambia algo cuando un admin lo desactiva. Lecturas y escrituras van por el pool
(rol que salta RLS), así que la autorización se comprueba aquí, como en el resto
de repositorios.
"""
from typing import Any, Dict, Optional

import psycopg

from src.db.pool import get_pool

_ADMIN_ROLES = ("owner", "admin")
_DEFAULT_ALLOW_EXTERNAL = True


class OrgLlmSettingsRepository:
    def _connect(self):
        return get_pool().connection()

    @staticmethod
    def _require_admin(cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s and role = any(%s)) as ok",
            (org_id, user_id, list(_ADMIN_ROLES)),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("owner/admin role required to change AI settings")

    @staticmethod
    def _read(cur: psycopg.Cursor, org_id: str) -> bool:
        cur.execute(
            "select allow_external_llm from public.org_llm_settings where org_id = %s",
            (org_id,),
        )
        row = cur.fetchone()
        return _DEFAULT_ALLOW_EXTERNAL if row is None else bool(row["allow_external_llm"])

    def get_settings(self, *, user_id: str, org_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_admin(cur, org_id, user_id)
                return {"org_id": org_id, "allow_external_llm": self._read(cur, org_id)}

    def set_settings(self, *, user_id: str, org_id: str,
                     allow_external_llm: bool) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_admin(cur, org_id, user_id)
                cur.execute(
                    """
                    insert into public.org_llm_settings
                        (org_id, allow_external_llm, updated_by, updated_at)
                    values (%s, %s, %s, now())
                    on conflict (org_id) do update
                       set allow_external_llm = excluded.allow_external_llm,
                           updated_by = excluded.updated_by,
                           updated_at = now()
                    """,
                    (org_id, allow_external_llm, user_id),
                )
            conn.commit()
        return {"org_id": org_id, "allow_external_llm": allow_external_llm}

    def allows_external_llm(self, org_id: str) -> bool:
        """Política interna (sin usuario): la consulta el guardián del LLM."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                return self._read(cur, org_id)

    def org_of(self, table: str, row_id: str) -> Optional[str]:
        """org_id de una fila (run, familia, acción, propuesta) para fijar el ámbito
        del LLM con la org REAL de los datos, no con un parámetro de la petición."""
        query = _ORG_LOOKUPS.get(table)
        if query is None:
            raise ValueError(f"tabla sin búsqueda de org: {table}")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (row_id,))
                row = cur.fetchone()
        return None if row is None else str(row["org_id"])


# Consultas fijas (sin SQL dinámico): la tabla viene de una lista cerrada.
_ORG_LOOKUPS = {
    "test_runs": "select org_id from public.test_runs where id::text = %s",
    "defect_families": "select org_id from public.defect_families where id::text = %s",
    "actions": "select org_id from public.actions where id::text = %s",
    "knowledge_proposals": "select org_id from public.knowledge_proposals where id::text = %s",
}
