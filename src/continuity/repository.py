"""Actas de traspaso: persistencia y permisos.

Patrón de los repos existentes: conexión del pool y membership-gated en cada
método. El rol del pooler bypasea RLS, así que el aislamiento real entre tenants
lo hacen estos checks, no la policy (la policy protege el acceso vía PostgREST).
"""
from typing import Any, Dict, Optional

import psycopg
from psycopg.types.json import Json

from src.db.pool import get_pool


class ContinuityRepository:
    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        return bool(cur.fetchone()["ok"])

    def is_org_admin(self, *, user_id: str, org_id: str) -> bool:
        """Emitir un acta de traspaso es un acto formal hacia el cliente → owner/admin,
        el mismo criterio que la emisión humana del acta de release."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("select exists(select 1 from public.memberships"
                        " where org_id=%s and user_id=%s and role in ('owner','admin')) as ok",
                        (org_id, user_id))
            return bool(cur.fetchone()["ok"])

    def save_act(self, *, user_id: str, org_id: str, project: str,
                 canonical_json: Dict[str, Any], signature: str,
                 score: Optional[int], created_by: str) -> Optional[Dict[str, Any]]:
        """Guarda el acta emitida. None si el usuario no es miembro de la org."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            cur.execute(
                "insert into public.handover_acts"
                " (org_id, project, canonical_json, signature, score, created_by)"
                " values (%s,%s,%s,%s,%s,%s) returning id",
                (org_id, project, Json(canonical_json), signature, score, created_by))
            row = cur.fetchone()
            conn.commit()
            return {"id": str(row["id"])}

    def latest_act(self, *, user_id: str, org_id: str,
                   project: str) -> Optional[Dict[str, Any]]:
        """La última acta del proyecto, o None si no hay ninguna (o no es miembro)."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            cur.execute(
                "select canonical_json, signature, score, project, created_at"
                " from public.handover_acts"
                " where org_id=%s and project=%s order by created_at desc limit 1",
                (org_id, project))
            row = cur.fetchone()
            if row is None:
                return None
            return {"canonical_json": row["canonical_json"], "signature": row["signature"],
                    "score": row["score"], "project": row["project"],
                    "created_at": row["created_at"].isoformat()}
