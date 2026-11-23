"""API de proyectos: listar (cualquier miembro); crear, renombrar y archivar (owner/admin).

La clave del proyecto es inmutable (la usan las ingestas y va dentro de las actas
firmadas); PATCH solo cambia el nombre visible, la descripción y el archivado. Las
ingestas crean el proyecto solas si no existe (trigger de la migración 036).
"""
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.orgs.access import OrgAccess, Resource, enforce, get_org_access
from src.orgs.permissions import Capability
from src.projects.repository import ProjectExists, ProjectRepository
from src.security import AuthenticatedUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/projects", tags=["projects"])

KEY_MAX = 200          # mismo tope que las ingestas (PROJECT_MAX_LEN)
NAME_MAX = 200
DESCRIPTION_MAX = 2000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_repo: Optional[ProjectRepository] = None


def get_project_repo() -> ProjectRepository:
    global _repo
    if _repo is None:
        _repo = ProjectRepository()
    return _repo


def _clean_line(value: Optional[str], *, field: str) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError(f"{field} no puede estar vacío")
    if _CONTROL.search(value):
        raise ValueError(f"{field} no admite saltos de línea ni caracteres de control")
    return value


class ProjectCreate(BaseModel):
    org_id: str
    key: str = Field(min_length=1, max_length=KEY_MAX)
    name: Optional[str] = Field(default=None, max_length=NAME_MAX)
    description: Optional[str] = Field(default=None, max_length=DESCRIPTION_MAX)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _clean_line(v, field="la clave")

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return _clean_line(v, field="el nombre")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=NAME_MAX)
    description: Optional[str] = Field(default=None, max_length=DESCRIPTION_MAX)
    archived: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return _clean_line(v, field="el nombre")


def _db_error(exc: Exception) -> HTTPException:
    logger.exception("projects: database error")
    return HTTPException(status_code=502, detail="Database error")


@router.get("", response_model=List[Dict[str, Any]])
def list_projects(
    org_id: str,
    include_archived: bool = True,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: ProjectRepository = Depends(get_project_repo),
) -> List[Dict[str, Any]]:
    enforce(access, user.user_id, Capability.READ, org_id=org_id)
    try:
        return repo.list(user_id=user.user_id, org_id=org_id, include_archived=include_archived)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_project(
    body: ProjectCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: ProjectRepository = Depends(get_project_repo),
) -> Dict[str, Any]:
    enforce(access, user.user_id, Capability.ADMIN, org_id=body.org_id)
    try:
        return repo.create(org_id=body.org_id, key=body.key, name=body.name or body.key,
                           description=body.description)
    except ProjectExists as exc:
        raise HTTPException(status_code=409,
                            detail="ya existe un proyecto con esa clave en la organización") from exc
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/{project_id}", response_model=Dict[str, Any])
def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: ProjectRepository = Depends(get_project_repo),
) -> Dict[str, Any]:
    try:
        uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="proyecto no encontrado") from None
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.PROJECT, project_id))
    try:
        row = repo.update(project_id=project_id, name=body.name,
                          description=body.description, archived=body.archived)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="proyecto no encontrado")
    return row
