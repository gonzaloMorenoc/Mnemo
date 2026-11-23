"""Gestión de miembros y del código de unión (owner/admin). Auditoría 23-nov, #11 / H3.

Las reglas (quién puede tocar a quién, no dejar la org sin owner…) viven en
src/orgs/member_rules.py y el repositorio las aplica dentro de la transacción.
"""
import logging
from typing import Any, Dict, List

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from src.api_v2 import _iso_or_none, get_repo
from src.multitenant_models import ChangeMemberRoleRequest, JoinCodeResponse, MemberResponse
from src.orgs.member_rules import LastOwnerError, MemberActionForbidden
from src.orgs.repository import MemberNotFound, OrganizationRepository
from src.security import AuthenticatedUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/orgs", tags=["orgs"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MemberActionForbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LastOwnerError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, MemberNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    logger.exception("orgs members: database error")
    return HTTPException(status_code=502, detail="Database error")


_HANDLED = (MemberActionForbidden, LastOwnerError, MemberNotFound, psycopg.Error)


def _member_response(row: Dict[str, Any]) -> MemberResponse:
    return MemberResponse(
        user_id=str(row["user_id"]), role=row["role"], email=row.get("email"),
        display_name=row.get("display_name"), created_at=_iso_or_none(row.get("created_at")),
    )


@router.get("/{org_id}/members", response_model=List[MemberResponse])
def list_members(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrganizationRepository = Depends(get_repo),
) -> List[MemberResponse]:
    try:
        rows = repo.list_members(actor_id=user.user_id, org_id=org_id)
    except _HANDLED as exc:
        raise _http_error(exc) from exc
    return [_member_response(r) for r in rows]


@router.patch("/{org_id}/members/{member_id}", response_model=Dict[str, str])
def change_member_role(
    org_id: str,
    member_id: str,
    body: ChangeMemberRoleRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrganizationRepository = Depends(get_repo),
) -> Dict[str, str]:
    try:
        row = repo.change_member_role(actor_id=user.user_id, org_id=org_id,
                                      target_id=member_id, new_role=body.role)
    except _HANDLED as exc:
        raise _http_error(exc) from exc
    return {"user_id": str(row["user_id"]), "role": row["role"]}


@router.delete("/{org_id}/members/{member_id}", response_model=Dict[str, bool])
def remove_member(
    org_id: str,
    member_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrganizationRepository = Depends(get_repo),
) -> Dict[str, bool]:
    try:
        repo.remove_member(actor_id=user.user_id, org_id=org_id, target_id=member_id)
    except _HANDLED as exc:
        raise _http_error(exc) from exc
    return {"removed": True}


@router.post("/{org_id}/join-code/rotate", response_model=JoinCodeResponse)
def rotate_join_code(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrganizationRepository = Depends(get_repo),
) -> JoinCodeResponse:
    """Invalida el código anterior y emite uno nuevo con caducidad."""
    try:
        row = repo.rotate_join_code(actor_id=user.user_id, org_id=org_id)
    except _HANDLED as exc:
        raise _http_error(exc) from exc
    return JoinCodeResponse(join_code=row["join_code"],
                            join_code_expires_at=_iso_or_none(row.get("join_code_expires_at")))
