"""Endpoints del interruptor de LLM externo por organización (solo owner/admin).

    GET /v2/orgs/{org_id}/llm-settings
    PUT /v2/orgs/{org_id}/llm-settings   {"allow_external_llm": false}

Con `allow_external_llm=false`, las funciones de IA de la org degradan como «sin
LLM» aunque el despliegue tenga un proveedor externo configurado (ver
src/llm/guard.py). Un proveedor local (Ollama) no se ve afectado: los datos no
salen de la máquina.
"""
import logging
from typing import Any, Dict

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src import config
from src.llm.org_policy import invalidate_policy_cache
from src.orgs.llm_settings import OrgLlmSettingsRepository
from src.security import AuthenticatedUser, get_current_user

logger = logging.getLogger(__name__)

# Sin prefijo: se monta dentro del router /v2 de src/api_v2.py.
router = APIRouter(tags=["v2"])

_EXTERNAL_PROVIDERS = ("openai", "anthropic")


class LlmSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_external_llm: bool


def get_llm_settings_repo() -> OrgLlmSettingsRepository:
    if not config.multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    return OrgLlmSettingsRepository()


def _with_context(settings: Dict[str, Any]) -> Dict[str, Any]:
    provider = (config.LLM_PROVIDER or "none").strip().lower()
    return {
        **settings,
        "provider": provider,
        "provider_is_external": provider in _EXTERNAL_PROVIDERS,
        "global_external_allowed": config.ALLOW_EXTERNAL_LLM,
    }


@router.get("/orgs/{org_id}/llm-settings", response_model=Dict[str, Any])
def get_llm_settings(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrgLlmSettingsRepository = Depends(get_llm_settings_repo),
) -> Dict[str, Any]:
    try:
        return _with_context(repo.get_settings(user_id=user.user_id, org_id=org_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.put("/orgs/{org_id}/llm-settings", response_model=Dict[str, Any])
def put_llm_settings(
    org_id: str,
    body: LlmSettingsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrgLlmSettingsRepository = Depends(get_llm_settings_repo),
) -> Dict[str, Any]:
    try:
        out = repo.set_settings(user_id=user.user_id, org_id=org_id,
                                allow_external_llm=body.allow_external_llm)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    invalidate_policy_cache(org_id)
    logger.info("org %s: allow_external_llm=%s (por %s)", org_id,
                body.allow_external_llm, user.user_id)
    return _with_context(out)
