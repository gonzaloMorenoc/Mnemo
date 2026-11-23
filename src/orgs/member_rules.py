"""Reglas puras de la gestión de miembros (sin BD: el repositorio las aplica dentro
de la transacción, con las filas bloqueadas)."""
from typing import Optional, Union

from src.orgs.permissions import Capability, OrgRole, parse_role, role_allows

RoleLike = Union[str, OrgRole, None]


class MemberActionForbidden(PermissionError):
    """El actor no tiene autoridad para esa operación sobre ese miembro."""


class LastOwnerError(ValueError):
    """La operación dejaría la organización sin ningún owner."""


def _require_manager(actor_role: RoleLike) -> OrgRole:
    if not role_allows(actor_role, Capability.ADMIN):
        raise MemberActionForbidden("solo owner/admin gestionan miembros")
    return OrgRole(actor_role)


def _forbid_touching_owner(actor: OrgRole, target: Optional[OrgRole]) -> None:
    if target is OrgRole.OWNER and actor is not OrgRole.OWNER:
        raise MemberActionForbidden("un admin no puede modificar a un owner")


def _forbid_last_owner(target: Optional[OrgRole], owner_count: int) -> None:
    if target is OrgRole.OWNER and owner_count <= 1:
        raise LastOwnerError("la organización no puede quedarse sin owner")


def check_role_change(*, actor_role: RoleLike, target_role: RoleLike, new_role: RoleLike,
                      is_self: bool, owner_count: int) -> OrgRole:
    """Valida un cambio de rol y devuelve el rol nuevo ya parseado."""
    new = parse_role(new_role)
    if new is None:
        raise ValueError(f"rol no válido: {new_role!r}")
    actor = _require_manager(actor_role)
    target = parse_role(target_role)
    if is_self and target is not None and new.rank > target.rank:
        raise MemberActionForbidden("nadie puede subirse de rol a sí mismo")
    _forbid_touching_owner(actor, target)
    if new.rank > actor.rank:
        raise MemberActionForbidden("no puedes asignar un rol superior al tuyo")
    if new is not OrgRole.OWNER:
        _forbid_last_owner(target, owner_count)
    return new


def check_removal(*, actor_role: RoleLike, target_role: RoleLike, is_self: bool,
                  owner_count: int) -> None:
    """Valida expulsar a un miembro (o salir uno mismo de la organización)."""
    target = parse_role(target_role)
    if not is_self:
        actor = _require_manager(actor_role)
        _forbid_touching_owner(actor, target)
    _forbid_last_owner(target, owner_count)
