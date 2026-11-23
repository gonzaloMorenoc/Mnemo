"""OrganizationRepository: código de unión (caduca, rota, solo admins lo ven) y
gestión de miembros (auditoría 23-nov, #11 / H3). Sin BD: cursor falso."""
from datetime import datetime, timezone

import psycopg
import pytest

from src.orgs.member_rules import LastOwnerError, MemberActionForbidden
from src.orgs.repository import (
    JOIN_CODE_TTL_DAYS,
    MemberNotFound,
    OrganizationRepository,
)

EXPIRES = datetime(2026, 12, 1, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, results):
        self.results = list(results)  # cola de resultados (fetchone o fetchall)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "set_config" in sql:
            return
        if self.results and isinstance(self.results[0], Exception):
            raise self.results.pop(0)

    def fetchone(self):
        return self.results.pop(0)

    def fetchall(self):
        return self.results.pop(0)


class _Conn:
    def __init__(self, cur):
        self.cur = cur
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def _repo(monkeypatch, results):
    cur = _Cursor(results)
    conn = _Conn(cur)
    monkeypatch.setattr(OrganizationRepository, "_connect", lambda self: conn)
    return OrganizationRepository(db_url="postgresql://fake"), cur, conn


def _org_row(role, code="abc123def0"):
    return {"id": "o1", "name": "Acme", "join_code": code, "join_code_expires_at": EXPIRES,
            "role": role, "created_at": "2026-11-01"}


# --- Código de unión -------------------------------------------------------------------

def test_list_hides_join_code_from_non_admins(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [[_org_row("viewer"), _org_row("member"), _org_row("admin")]])
    orgs = repo.list_user_organizations(user_id="u1")
    assert [o["join_code"] for o in orgs] == [None, None, "abc123def0"]
    assert orgs[0]["join_code_expires_at"] is None
    assert orgs[2]["join_code_expires_at"] == EXPIRES


def test_join_returns_viewer_without_join_code(monkeypatch):
    repo, _, conn = _repo(monkeypatch, [{"org_id": "o1"}, _org_row("viewer")])
    org = repo.join_organization(user_id="u1", join_code="ABC123DEF0")
    assert org["role"] == "viewer"
    assert org["join_code"] is None
    assert conn.committed


def test_join_with_invalid_code_is_a_value_error_not_a_db_error(monkeypatch):
    """La función SQL lanza `raise exception`: antes salía como 502 y no contaba
    para el freno de fuerza bruta."""
    repo, _, _ = _repo(monkeypatch, [psycopg.errors.RaiseException("invalid join code")])
    with pytest.raises(ValueError, match="no válido"):
        repo.join_organization(user_id="u1", join_code="nope")


def test_join_with_expired_code_says_so(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [psycopg.errors.RaiseException("expired join code")])
    with pytest.raises(ValueError, match="caducado"):
        repo.join_organization(user_id="u1", join_code="old")


def test_rotate_requires_admin(monkeypatch):
    repo, cur, _ = _repo(monkeypatch, [{"role": "member"}])
    with pytest.raises(MemberActionForbidden):
        repo.rotate_join_code(actor_id="u1", org_id="o1")
    assert not any("update public.organizations" in sql for sql, _ in cur.executed)


def test_rotate_sets_new_code_and_expiry(monkeypatch):
    repo, cur, conn = _repo(monkeypatch, [{"role": "admin"},
                                          {"join_code": "x", "join_code_expires_at": EXPIRES}])
    out = repo.rotate_join_code(actor_id="u1", org_id="o1")
    sql, params = cur.executed[-1]
    assert "update public.organizations" in sql
    new_code, ttl, org_id = params
    assert len(new_code) >= 10 and new_code != "abc123def0"
    assert ttl == JOIN_CODE_TTL_DAYS
    assert org_id == "o1"
    assert out == {"join_code": "x", "join_code_expires_at": EXPIRES}
    assert conn.committed


# --- Miembros ----------------------------------------------------------------------------

_MEMBERS = [
    {"user_id": "owner-1", "role": "owner"},
    {"user_id": "admin-1", "role": "admin"},
    {"user_id": "viewer-1", "role": "viewer"},
]


def test_list_members_requires_admin(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [{"role": "viewer"}])
    with pytest.raises(MemberActionForbidden):
        repo.list_members(actor_id="viewer-1", org_id="o1")


def test_list_members_includes_email_and_name(monkeypatch):
    rows = [{"user_id": "u2", "role": "member", "email": "a@b.c", "display_name": "Ana",
             "created_at": "2026-11-01"}]
    repo, cur, _ = _repo(monkeypatch, [{"role": "owner"}, rows])
    assert repo.list_members(actor_id="u1", org_id="o1") == rows
    sql = cur.executed[-1][0]
    assert "auth.users" in sql and "public.profiles" in sql


def test_admin_promotes_viewer(monkeypatch):
    repo, cur, conn = _repo(monkeypatch, [_MEMBERS, {"user_id": "viewer-1", "role": "member"}])
    out = repo.change_member_role(actor_id="admin-1", org_id="o1",
                                  target_id="viewer-1", new_role="member")
    assert out["role"] == "member"
    assert "for update" in cur.executed[0][0]
    assert conn.committed


def test_admin_cannot_demote_owner(monkeypatch):
    repo, cur, conn = _repo(monkeypatch, [_MEMBERS])
    with pytest.raises(MemberActionForbidden):
        repo.change_member_role(actor_id="admin-1", org_id="o1",
                                target_id="owner-1", new_role="viewer")
    assert len(cur.executed) == 1
    assert not conn.committed


def test_last_owner_cannot_demote_themselves(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [_MEMBERS])
    with pytest.raises(LastOwnerError):
        repo.change_member_role(actor_id="owner-1", org_id="o1",
                                target_id="owner-1", new_role="admin")


def test_change_role_of_non_member_is_not_found(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [_MEMBERS])
    with pytest.raises(MemberNotFound):
        repo.change_member_role(actor_id="owner-1", org_id="o1",
                                target_id="ghost", new_role="member")


def test_outsider_cannot_manage_members(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [_MEMBERS])
    with pytest.raises(MemberActionForbidden):
        repo.change_member_role(actor_id="intruso", org_id="o1",
                                target_id="viewer-1", new_role="member")


def test_admin_removes_viewer(monkeypatch):
    repo, cur, conn = _repo(monkeypatch, [_MEMBERS])
    repo.remove_member(actor_id="admin-1", org_id="o1", target_id="viewer-1")
    sql, params = cur.executed[-1]
    assert sql.strip().startswith("delete from public.memberships")
    assert params == ("o1", "viewer-1")
    assert conn.committed


def test_admin_cannot_remove_owner(monkeypatch):
    repo, _, conn = _repo(monkeypatch, [_MEMBERS])
    with pytest.raises(MemberActionForbidden):
        repo.remove_member(actor_id="admin-1", org_id="o1", target_id="owner-1")
    assert not conn.committed


def test_remove_unknown_member_is_not_found(monkeypatch):
    repo, _, _ = _repo(monkeypatch, [_MEMBERS])
    with pytest.raises(MemberNotFound):
        repo.remove_member(actor_id="owner-1", org_id="o1", target_id="ghost")
