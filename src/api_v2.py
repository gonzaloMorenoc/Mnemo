from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.config import multi_tenant_enabled
from src.defects.ingestion_service import IngestionService
from src.defects.repository import AssuranceRepository
from src.assurance.narrator import LLMNarrator, Narrator
from src.assurance.verdict import build_verdict
from src.jira.client import JiraApiError
from src.jira.integrations_repository import IntegrationsRepository
from src.jira.ingestion_service import JiraIngestionService
from src.jira.safe_url import validate_base_url
from src.multitenant_models import (
    AnalyzeV2Request,
    AnalyzeV2Response,
    AssuranceVerdictResponse,
    CreateOrgRequest,
    DefectFamilyResponse,
    DefectFamilySummary,
    DefectLineageResponse,
    FailureRef,
    FamilyVerdict,
    IngestReportResponse,
    JiraConfigRequest,
    JiraConfigResponse,
    JiraIngestResponse,
    JiraPullRequest,
    JoinOrgRequest,
    OrganizationResponse,
    RootCauseResponse,
    ScopeSource,
    StructuredAnalysisPayload,
    UploadResponse,
)
from src.security import AuthenticatedUser, get_current_user
from src.structured_analyzer import StructuredAnalyzer
from src.tenant_kb import TenantKBRepository

router = APIRouter(prefix="/v2", tags=["v2"])

# Singletons perezosos (sin anotacion PEP 604 para compatibilidad <3.10)
_repo = None
_analyzer = None
_assurance_repo = None
_ingestion_service = None
_narrator = None
_root_cause_analyzer = None
_integrations_repo = None
_jira_service = None


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


def get_assurance_repo() -> AssuranceRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _assurance_repo
    if _assurance_repo is None:
        _assurance_repo = AssuranceRepository()
    return _assurance_repo


def get_ingestion_service() -> IngestionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _ingestion_service
    if _ingestion_service is None:
        from src.defects.embedder import LocalEmbedder
        _ingestion_service = IngestionService(repo=get_assurance_repo(), embedder=LocalEmbedder())
    return _ingestion_service


def get_narrator() -> Narrator:
    global _narrator
    if _narrator is None:
        from src.llm.factory import get_llm_provider
        _narrator = LLMNarrator(get_llm_provider())
    return _narrator


def get_root_cause_analyzer():
    global _root_cause_analyzer
    if _root_cause_analyzer is None:
        from src.assurance.root_cause import RootCauseAnalyzer
        from src.llm.factory import get_llm_provider
        _root_cause_analyzer = RootCauseAnalyzer(get_llm_provider())
    return _root_cause_analyzer


def get_integrations_repo() -> IntegrationsRepository:
    global _integrations_repo
    if _integrations_repo is None:
        _integrations_repo = IntegrationsRepository()
    return _integrations_repo


def get_jira_ingestion_service() -> JiraIngestionService:
    global _jira_service
    if _jira_service is None:
        from src.defects.embedder import LocalEmbedder
        _jira_service = JiraIngestionService(
            repo=get_assurance_repo(), embedder=LocalEmbedder(),
            integrations=get_integrations_repo(),
        )
    return _jira_service


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


def _org_to_response(org: Dict[str, Any]) -> OrganizationResponse:
    return OrganizationResponse(
        id=str(org["id"]),
        name=org["name"],
        join_code=org["join_code"],
        role=org.get("role"),
        created_at=str(org["created_at"]) if org.get("created_at") is not None else None,
    )


@router.get("/orgs", response_model=List[OrganizationResponse])
def list_orgs(
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> List[OrganizationResponse]:
    try:
        orgs = repo.list_user_organizations(user_id=user.user_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [_org_to_response(o) for o in orgs]


@router.post("/orgs", response_model=OrganizationResponse)
def create_org(
    req: CreateOrgRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> OrganizationResponse:
    try:
        org = repo.create_organization(user_id=user.user_id, name=req.name)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if org is None:
        raise HTTPException(status_code=502, detail="Organization could not be created")
    return _org_to_response(org)


@router.post("/orgs/join", response_model=OrganizationResponse)
def join_org(
    req: JoinOrgRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> OrganizationResponse:
    try:
        org = repo.join_organization(user_id=user.user_id, join_code=req.join_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if org is None:
        raise HTTPException(status_code=502, detail="Joined organization could not be loaded")
    return _org_to_response(org)


@router.post("/upload", response_model=UploadResponse)
def upload_v2(
    file: UploadFile = File(...),
    scope: str = Form("user"),
    org_id: Optional[str] = Form(None),
    contribute_global: bool = Form(False),
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> UploadResponse:
    try:
        data = file.file.read()
        result = repo.ingest_file(
            user_id=user.user_id,
            filename=file.filename or "upload.txt",
            data=data,
            scope=scope,
            org_id=org_id,
            contribute_global=contribute_global,
            mime_type=file.content_type,
        )
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Could not read uploaded file") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc

    return UploadResponse(
        document_id=str(result.document_id),
        global_document_id=str(result.global_document_id) if result.global_document_id else None,
        chunk_count=result.chunk_count,
        storage_path=result.storage_path,
    )


@router.get("/health")
def health_v2() -> Dict[str, Any]:
    return {"status": "active", "multi_tenant_enabled": multi_tenant_enabled()}


@router.post("/ingest/report", response_model=IngestReportResponse)
def ingest_report_v2(
    file: UploadFile = File(...),
    project: str = Form(...),
    source: str = Form("auto"),
    org_id: str = Form(...),
    user: AuthenticatedUser = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestReportResponse:
    try:
        data = file.file.read()
        result = service.ingest_report(
            user_id=user.user_id, org_id=org_id, project=project, source=source, data=data
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return IngestReportResponse(**result)


@router.post("/integrations/jira", response_model=JiraConfigResponse)
def set_jira_integration(
    body: JiraConfigRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> JiraConfigResponse:
    try:
        base = validate_base_url(body.base_url)
        integrations.upsert_jira_config(
            user_id=user.user_id, org_id=body.org_id, base_url=base,
            email=body.email, token=body.token, jql=body.jql,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraConfigResponse(configured=True, base_url=base, email=body.email, jql=body.jql)


@router.get("/integrations/jira", response_model=JiraConfigResponse)
def get_jira_integration(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> JiraConfigResponse:
    try:
        cfg = integrations.get_jira_config(user_id=user.user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraConfigResponse(**cfg)


@router.post("/ingest/jira/file", response_model=JiraIngestResponse)
def ingest_jira_file(
    file: UploadFile = File(...),
    project: str = Form(...),
    org_id: str = Form(...),
    user: AuthenticatedUser = Depends(get_current_user),
    service: JiraIngestionService = Depends(get_jira_ingestion_service),
) -> JiraIngestResponse:
    try:
        data = file.file.read()
        result = service.ingest_from_export(
            user_id=user.user_id, org_id=org_id, project=project, data=data)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraIngestResponse(**result)


@router.post("/ingest/jira/pull", response_model=JiraIngestResponse)
def ingest_jira_pull(
    body: JiraPullRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: JiraIngestionService = Depends(get_jira_ingestion_service),
) -> JiraIngestResponse:
    try:
        result = service.ingest_from_pull(
            user_id=user.user_id, org_id=body.org_id, project=body.project)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status_code=502, detail=f"Jira API error: {exc}") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraIngestResponse(**result)


@router.get("/defects", response_model=List[DefectFamilyResponse])
def list_defects_v2(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> List[DefectFamilyResponse]:
    try:
        rows = repo.list_defects(user_id=user.user_id, org_id=org_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [DefectFamilyResponse(**r) for r in rows]


@router.get("/defects/{defect_id}", response_model=DefectLineageResponse)
def defect_lineage_v2(
    defect_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> DefectLineageResponse:
    try:
        data = repo.get_lineage(user_id=user.user_id, defect_id=defect_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    family = DefectFamilySummary(**data["family"]) if data["family"] else None
    return DefectLineageResponse(family=family, failures=[FailureRef(**f) for f in data["failures"]])


@router.post("/defects/{defect_id}/root-cause", response_model=RootCauseResponse)
def root_cause_v2(
    defect_id: str,
    regenerate: bool = False,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    analyzer=Depends(get_root_cause_analyzer),
) -> RootCauseResponse:
    try:
        data = repo.get_family_with_failures(user_id=user.user_id, defect_id=defect_id)
        if data is None:
            raise HTTPException(status_code=404, detail="defecto no encontrado")
        cached = data["family"].get("root_cause")
        if cached and not regenerate:
            return RootCauseResponse(defect_id=defect_id, root_cause=cached, cached=True)
        text = analyzer.analyze(data["family"], data["failures"])
        text = (text or "")[:8000]
        repo.save_root_cause(user_id=user.user_id, defect_id=defect_id, text=text)
        return RootCauseResponse(defect_id=defect_id, root_cause=text, cached=False)
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001 — fallo del LLM/proveedor
        raise HTTPException(status_code=503, detail="el análisis IA no está disponible") from exc


@router.get("/assurance/run/{run_id}", response_model=AssuranceVerdictResponse)
def assurance_verdict_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    narrator: Narrator = Depends(get_narrator),
) -> AssuranceVerdictResponse:
    try:
        data = repo.get_run_assurance_data(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if data["run"] is None:
        raise HTTPException(status_code=404, detail="run not found")
    verdict = build_verdict(run_summary=data["summary"], run_families=data["families"])
    try:
        narrative = narrator.summarize(verdict)
    except Exception:
        # La narrativa LLM es opcional: si el narrator (Ollama) falla, devolvemos
        # el veredicto determinista sin narrativa en lugar de romper la respuesta.
        narrative = None
    return AssuranceVerdictResponse(
        run_id=run_id,
        ingested=verdict["ingested"], known=verdict["known"], novel=verdict["novel"],
        risk=verdict["risk"],
        top_families=[FamilyVerdict(**f) for f in verdict["top_families"]],
        narrative=narrative,
    )
