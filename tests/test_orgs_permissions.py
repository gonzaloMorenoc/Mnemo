"""Matriz de permisos por rol (auditoría 23-nov, #10/#11, H2/H3/H8).

viewer = solo lectura · member = trabajo diario de QA · owner/admin = configurar,
publicar, escribir en repos del cliente, emitir actas y gestionar miembros."""
import pytest

from src.orgs.permissions import Capability, OrgRole, parse_role, role_allows

_MATRIX = [
    # (rol, capacidad, permitido)
    ("viewer", Capability.READ, True),
    ("viewer", Capability.QA_WORK, False),
    ("viewer", Capability.ADMIN, False),
    ("member", Capability.READ, True),
    ("member", Capability.QA_WORK, True),
    ("member", Capability.ADMIN, False),
    ("admin", Capability.READ, True),
    ("admin", Capability.QA_WORK, True),
    ("admin", Capability.ADMIN, True),
    ("owner", Capability.READ, True),
    ("owner", Capability.QA_WORK, True),
    ("owner", Capability.ADMIN, True),
]


@pytest.mark.parametrize("role,capability,allowed", _MATRIX)
def test_role_matrix(role, capability, allowed):
    assert role_allows(role, capability) is allowed


@pytest.mark.parametrize("capability", list(Capability))
def test_no_role_means_no_access(capability):
    assert role_allows(None, capability) is False


@pytest.mark.parametrize("capability", list(Capability))
def test_unknown_role_is_denied(capability):
    assert role_allows("superuser", capability) is False


def test_parse_role_accepts_enum_and_string():
    assert parse_role("viewer") is OrgRole.VIEWER
    assert parse_role(OrgRole.OWNER) is OrgRole.OWNER
    assert parse_role("nope") is None
    assert parse_role(None) is None


def test_role_rank_orders_roles():
    assert OrgRole.VIEWER.rank < OrgRole.MEMBER.rank < OrgRole.ADMIN.rank < OrgRole.OWNER.rank
