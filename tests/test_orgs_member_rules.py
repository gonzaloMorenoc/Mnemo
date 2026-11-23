"""Reglas de la gestión de miembros (auditoría 23-nov, #11 / H3).

- solo owner/admin gestionan miembros;
- la org nunca se queda sin owner;
- un admin no toca a un owner (ni crea owners);
- nadie se sube de rol a sí mismo."""
import pytest

from src.orgs.member_rules import (
    LastOwnerError,
    MemberActionForbidden,
    check_removal,
    check_role_change,
)


def _change(actor_role, target_role, new_role, *, self_change=False, owners=2):
    check_role_change(actor_role=actor_role, target_role=target_role, new_role=new_role,
                      is_self=self_change, owner_count=owners)


def test_admin_promotes_viewer_to_member():
    _change("admin", "viewer", "member")


def test_owner_promotes_member_to_owner():
    _change("owner", "member", "owner")


@pytest.mark.parametrize("actor", ["viewer", "member", None])
def test_non_admins_cannot_change_roles(actor):
    with pytest.raises(MemberActionForbidden):
        _change(actor, "viewer", "member")


def test_admin_cannot_touch_an_owner():
    with pytest.raises(MemberActionForbidden):
        _change("admin", "owner", "member")


def test_admin_cannot_create_owners():
    with pytest.raises(MemberActionForbidden):
        _change("admin", "member", "owner")


def test_nobody_promotes_themselves():
    with pytest.raises(MemberActionForbidden):
        _change("admin", "admin", "owner", self_change=True)


def test_self_demotion_is_allowed_if_another_owner_remains():
    _change("owner", "owner", "admin", self_change=True, owners=2)


def test_last_owner_cannot_be_demoted():
    with pytest.raises(LastOwnerError):
        _change("owner", "owner", "admin", self_change=True, owners=1)


def test_unknown_new_role_is_rejected():
    with pytest.raises(ValueError):
        _change("owner", "member", "superuser")


def test_admin_removes_member():
    check_removal(actor_role="admin", target_role="member", is_self=False, owner_count=1)


def test_admin_cannot_remove_owner():
    with pytest.raises(MemberActionForbidden):
        check_removal(actor_role="admin", target_role="owner", is_self=False, owner_count=2)


def test_member_cannot_remove_others():
    with pytest.raises(MemberActionForbidden):
        check_removal(actor_role="member", target_role="viewer", is_self=False, owner_count=1)


def test_last_owner_cannot_be_removed():
    with pytest.raises(LastOwnerError):
        check_removal(actor_role="owner", target_role="owner", is_self=True, owner_count=1)


def test_owner_removes_another_owner_when_two_remain():
    check_removal(actor_role="owner", target_role="owner", is_self=False, owner_count=2)


def test_anyone_can_leave_the_org():
    check_removal(actor_role="viewer", target_role="viewer", is_self=True, owner_count=1)
