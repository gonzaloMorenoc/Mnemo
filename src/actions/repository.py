from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.config import DATABASE_URL


class ActionRepository:
    """Acceso a datos de la capa de acción (tabla public.actions). El pooler hace
    BYPASS de RLS → cada método valida membership en la capa de app."""

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.db_url, row_factory=dict_row)

    def _set_claims(self, conn: psycopg.Connection, user_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def _rows(self, cur) -> List[Dict[str, Any]]:
        return [
            {"id": str(r["id"]), "triage_verdict_id": str(r["triage_verdict_id"]),
             "run_id": str(r["run_id"]), "org_id": str(r["org_id"]), "kind": r["kind"],
             "payload": r["payload"], "summary": r["summary"], "status": r["status"],
             "artifact_ref": r["artifact_ref"],
             "approved_by": str(r["approved_by"]) if r["approved_by"] else None,
             "approved_at": r["approved_at"].isoformat() if r["approved_at"] else None,
             "reject_reason": r["reject_reason"]}
            for r in cur.fetchall()
        ]

    def save_actions(self, *, user_id: str, org_id: str, run_id: str,
                     actions: List[Dict[str, Any]]) -> int:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute("select 1 from public.test_runs where id = %s and org_id = %s",
                            (run_id, org_id))
                if cur.fetchone() is None:
                    raise ValueError("run does not belong to the organization")
                cur.execute("delete from public.actions where run_id = %s and status = 'proposed'",
                            (run_id,))
                for a in actions:
                    cur.execute(
                        "insert into public.actions"
                        " (triage_verdict_id, run_id, org_id, kind, payload, summary)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (a["triage_verdict_id"], run_id, org_id, a["kind"],
                         Json(a.get("payload")), a.get("summary")),
                    )
            conn.commit()
        return len(actions)

    _COLS = ("id, triage_verdict_id, run_id, org_id, kind, payload, summary, status,"
             " artifact_ref, approved_by, approved_at, reject_reason")

    def list_actions_for_run(self, *, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        """Acciones propuestas de un run (membership vía la propia fila). [] si no es miembro."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"select {self._COLS} from public.actions a"
                    " where a.run_id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = a.org_id and m.user_id = %s)"
                    " order by a.created_at desc",
                    (run_id, user_id),
                )
                return self._rows(cur)

    def get_actions(self, *, user_id: str, org_id: str,
                    status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return []
                if status:
                    cur.execute(f"select {self._COLS} from public.actions"
                                " where org_id = %s and status = %s order by created_at desc",
                                (org_id, status))
                else:
                    cur.execute(f"select {self._COLS} from public.actions"
                                " where org_id = %s order by created_at desc", (org_id,))
                return self._rows(cur)

    def get_action(self, *, user_id: str, action_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"select {self._COLS} from public.actions a"
                    " where a.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = a.org_id and m.user_id = %s)",
                    (action_id, user_id),
                )
                rows = self._rows(cur)
                return rows[0] if rows else None

    def approve_action(self, *, user_id: str, action_id: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'approved',"
                    "  approved_by = %s, approved_at = now()"
                    " where a.id = %s and a.status = 'proposed'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s"
                    "       and m.role in ('owner','admin'))",
                    (user_id, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def materialize_action(self, *, user_id: str, action_id: str, artifact_ref: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a"
                    " set status = 'materialized', artifact_ref = %s, materializing_at = null"
                    " where a.id = %s and a.status = 'materializing'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s"
                    "       and m.role in ('owner','admin'))",
                    (artifact_ref, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def mark_materializing(self, *, user_id: str, action_id: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'materializing', materializing_at = now()"
                    " where a.id = %s"
                    "   and (a.status = 'approved'"
                    "        or (a.status = 'materializing'"
                    "            and a.materializing_at < now() - interval '15 minutes'))"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s"
                    "       and m.role in ('owner','admin'))",
                    (action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def revert_to_approved(self, *, user_id: str, action_id: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'approved', materializing_at = null"
                    " where a.id = %s and a.status = 'materializing'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s"
                    "       and m.role in ('owner','admin'))",
                    (action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def reject_action(self, *, user_id: str, action_id: str, reason: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'rejected', reject_reason = %s"
                    " where a.id = %s and a.status = 'proposed'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s"
                    "       and m.role in ('owner','admin'))",
                    (reason, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok
