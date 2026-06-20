from typing import Any, Dict, List

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from src.config import multi_tenant_enabled
from src.multitenant_models import (
    AnalyzeV2Request,
    AnalyzeV2Response,
    ScopeSource,
    StructuredAnalysisPayload,
)
from src.security import AuthenticatedUser, get_current_user
from src.structured_analyzer import StructuredAnalyzer
from src.tenant_kb import TenantKBRepository

router = APIRouter(prefix="/v2", tags=["v2"])

# Singletons perezosos (sin anotacion PEP 604 para compatibilidad <3.10)
_repo = None
_analyzer = None


def get_repo() -> TenantKBRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _repo
    if _repo is None:
        _repo = TenantKBRepository()
    return _repo


def get_analyzer() -> StructuredAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = StructuredAnalyzer()
    return _analyzer


def _unique_scopes(contexts: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for c in contexts:
        if c["scope"] not in seen:
            seen.append(c["scope"])
    return seen


@router.post("/analyze", response_model=AnalyzeV2Response)
def analyze_v2(
    req: AnalyzeV2Request,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
    analyzer: StructuredAnalyzer = Depends(get_analyzer),
) -> AnalyzeV2Response:
    try:
        contexts = repo.retrieve_context(
            user_id=user.user_id, query=req.error_log, org_id=req.org_id, top_k=req.top_k
        )
        analysis = analyzer.analyze(error_log=req.error_log, contexts=contexts)
        source_scopes = _unique_scopes(contexts)
        analysis_id = repo.save_analysis(
            user_id=user.user_id,
            org_id=req.org_id,
            input_error=req.error_log,
            output=analysis,
            confidence=float(analysis["confidence"]),
            source_scopes=source_scopes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc

    return AnalyzeV2Response(
        analysis=StructuredAnalysisPayload(**analysis),
        sources=[
            ScopeSource(scope=c["scope"], source_title=c["source_title"], similarity=c["similarity"])
            for c in contexts
        ],
        source_scopes=source_scopes,
        analysis_id=analysis_id,
    )
