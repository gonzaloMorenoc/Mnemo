"""Matriz de permisos por rol: la ÚNICA fuente de verdad de qué puede hacer cada rol.

- viewer: solo lectura en todo, incluido preguntar a la memoria (preguntar es leer).
- member: trabajo diario de QA (subir informes, etiquetar familias, crear/editar
  conocimiento, resolver desempates, generar planes/tests).
- owner/admin: configurar integraciones y tokens de ingesta, publicar el gate,
  aprobar/aplicar acciones que escriben en repos del cliente, emitir actas y
  gestionar miembros.

Los endpoints piden una `Capability`; nunca comparan roles a mano.
"""
from enum import Enum
from typing import Optional, Union


class OrgRole(str, Enum):
    VIEWER = "viewer"
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]


_ROLE_RANK = {
    OrgRole.VIEWER: 0,
    OrgRole.MEMBER: 1,
    OrgRole.ADMIN: 2,
    OrgRole.OWNER: 3,
}


class Capability(str, Enum):
    READ = "read"
    QA_WORK = "qa_work"
    ADMIN = "admin"


_MIN_ROLE = {
    Capability.READ: OrgRole.VIEWER,
    Capability.QA_WORK: OrgRole.MEMBER,
    Capability.ADMIN: OrgRole.ADMIN,
}

# Rol con el que entra quien usa el código de unión: un admin lo sube después.
JOIN_ROLE = OrgRole.VIEWER


def parse_role(value: Union[str, OrgRole, None]) -> Optional[OrgRole]:
    if value is None:
        return None
    try:
        return OrgRole(value)
    except ValueError:
        return None


def role_allows(role: Union[str, OrgRole, None], capability: Capability) -> bool:
    parsed = parse_role(role)
    if parsed is None:
        return False
    return parsed.rank >= _MIN_ROLE[capability].rank
