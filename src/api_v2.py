import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

logger = logging.getLogger(__name__)

from src.certify.gate import GateService
from src.certify.repository import CertificateRepository
from src.certify.render import render_html
from src.certify.service import CertificateService
from src.certify.signing import SigningKeyMissing, canonical_json, verify
from src.config import (CI_MAX_BODY_BYTES, CI_SERVICE_ORG_ID, CI_SERVICE_USER_ID,
                        CI_WEBHOOK_SECRET, LLM_MODEL, MNEMO_SIGNING_PRIVATE_KEY,
                        MNEMO_SIGNING_PUBLIC_KEY, MNEMO_VERSION, multi_tenant_enabled)
from src.actions.quarantine import QuarantineActuator
from src.actions.repository import ActionRepository
from src.actions.selfheal.selfheal import SelfHealActuator
from src.actions.service import ActionService
from src.actions.ticket import TicketActuator
from src.ci.github_app import GitHubCodeHost, GitHubError
from src.ci.github_auth import GitHubAppAuth, GitHubAuthError
from src.ci.ingestion_service import CiIngestionService
from src.triage.service import TriageService
from src.ci.models import CiRunArtifact
from src.ci.webhook_auth import verify_signature
from src.defects.ingestion_service import IngestionService
from src.defects.repository import AssuranceRepository
from src.assurance.narrator import LLMNarrator, Narrator
from src.assurance.verdict import build_verdict
from src.jira.client import JiraApiError
from src.jira.integrations_repository import IntegrationsRepository
from src.jira.ingestion_service import JiraIngestionService
from src.jira.safe_url import validate_base_url
from src.multitenant_models import (
    ActionApproveResponse,
    ActionRejectRequest,
    ActionRejectResponse,
    ActionResponse,
    AnalyzeV2Request,
    AnalyzeV2Response,
    AssuranceVerdictResponse,
    CalibrationMetricsResponse,
    CertificateResponse,
    CertificateVerifyRequest,
    CertificateVerifyResponse,
    FamilyLabelResponse,
    GateResponse,
    CiWebhookResponse,
    CreateOrgRequest,
    DefectFamilyResponse,
    DefectFamilySummary,
    DefectLineageResponse,
    FailureRef,
    FamilyVerdict,
    GitHubConfigRequest,
    GitHubConfigResponse,
    IngestReportResponse,
    JiraConfigRequest,
    JiraConfigResponse,
    JiraIngestResponse,
    JiraPullRequest,
    JoinOrgRequest,
    OrganizationResponse,
    ProposeActionsResponse,
    RootCauseResponse,
    ScopeSource,
    SetFamilyLabelRequest,
    StructuredAnalysisPayload,
    TriageVerdictResponse,
    UploadResponse,
)
from src.security import AuthenticatedUser, get_current_user
from src.structured_analyzer import StructuredAnalyzer
from src.tenant_kb import TenantKBRepository

router = APIRouter(prefix="/v2", tags=["v2"])

_ACTION_STATUSES = {"proposed", "approved", "rejected", "materialized", "materializing"}

# Singletons perezosos (sin anotacion PEP 604 para compatibilidad <3.10)
_repo = None
_analyzer = None
_assurance_repo = None
_ingestion_service = None
_narrator = None
_root_cause_analyzer = None
_integrations_repo = None
_jira_service = None
_ci_ingestion_service = None
_triage_service = None
_action_service = None
_action_repo = None
_github_auth = None
_cert_repo = None
_certificate_service = None
_gate_service = None


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


def get_ci_ingestion_service() -> CiIngestionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _ci_ingestion_service
    if _ci_ingestion_service is None:
        from src.defects.embedder import LocalEmbedder
        _ci_ingestion_service = CiIngestionService(
            repo=get_assurance_repo(), embedder=LocalEmbedder()
        )
    return _ci_ingestion_service


def get_triage_service() -> TriageService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _triage_service
    if _triage_service is None:
        _triage_service = TriageService(repo=get_assurance_repo())
    return _triage_service


def get_action_repo() -> ActionRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _action_repo
    if _action_repo is None:
        _action_repo = ActionRepository()
    return _action_repo


def _get_github_auth() -> GitHubAppAuth:
    global _github_auth
    if _github_auth is None:
        _github_auth = GitHubAppAuth()   # lee env perezosamente
    return _github_auth


def _github_codehost_factory(org_id: str, user_id: str) -> GitHubCodeHost:
    cfg = get_integrations_repo().get_github_config(user_id=user_id, org_id=org_id)
    if not cfg.get("configured"):
        raise ValueError("GitHub no configurado para el org")
    if not cfg.get("installation_id") or not cfg.get("repo_full_name"):
        raise ValueError("GitHub integration incompleta para el org (falta installation_id o repo)")
    return GitHubCodeHost(auth=_get_github_auth(),
                          installation_id=cfg["installation_id"],
                          repo_full_name=cfg["repo_full_name"])


class _LazyRootCauseAnalyzer:
    """Construye el RootCauseAnalyzer (y su LLM) en tiempo de análisis, no al crear el
    singleton: una mala config del LLM degrada el ticket ('no disponible') en vez de
    tumbar el servicio de acciones con un 500."""

    def analyze(self, family, failures):
        return get_root_cause_analyzer().analyze(family, failures)


class _LazySelfHealExplainer:
    """Construye el explainer LLM en tiempo de uso (mala config del LLM → degrada a plantilla)."""

    def explain(self, **kw):
        from src.actions.selfheal.explainer import LLMSelfHealExplainer
        from src.llm.factory import get_llm_provider
        return LLMSelfHealExplainer(get_llm_provider()).explain(**kw)


def get_action_service() -> ActionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _action_service
    if _action_service is None:
        _action_service = ActionService(
            repo=get_assurance_repo(),
            actions_repo=get_action_repo(),
            actuators={
                "flaky": QuarantineActuator(),
                "real": TicketActuator(_LazyRootCauseAnalyzer()),
                "maintenance": SelfHealActuator(explainer=_LazySelfHealExplainer()),
            },
            codehost_factory=_github_codehost_factory,
        )
    return _action_service


def get_certificate_repo() -> CertificateRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _cert_repo
    if _cert_repo is None:
        _cert_repo = CertificateRepository()
    return _cert_repo


def get_certificate_service() -> CertificateService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _certificate_service
    if _certificate_service is None:
        _certificate_service = CertificateService(
            repo=get_assurance_repo(), cert_repo=get_certificate_repo(),
            private_key=MNEMO_SIGNING_PRIVATE_KEY, public_key=MNEMO_SIGNING_PUBLIC_KEY,
            mnemo_version=MNEMO_VERSION, model_version=LLM_MODEL or "unknown",
        )
    return _certificate_service


def get_gate_service() -> GateService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _gate_service
    if _gate_service is None:
        _gate_service = GateService(repo=get_assurance_repo(), cert_repo=get_certificate_repo(),
                                    codehost_factory=_github_codehost_factory)
    return _gate_service


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


@router.post("/ci/webhook", response_model=CiWebhookResponse)
async def ci_webhook(request: Request) -> CiWebhookResponse:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > CI_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    body = await request.body()
    if len(body) > CI_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, CI_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="invalid signature")
    if not CI_SERVICE_USER_ID:
        raise HTTPException(status_code=503, detail="CI service account not configured")
    try:
        artifact = CiRunArtifact.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid artifact") from exc
    if CI_SERVICE_ORG_ID and artifact.org_id != CI_SERVICE_ORG_ID:
        raise HTTPException(status_code=403, detail="org_id not allowed for this CI account")
    service = get_ci_ingestion_service()
    try:
        result = service.ingest_artifact(user_id=CI_SERVICE_USER_ID, artifact=artifact)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    triage_summary = None
    if not result.get("deduplicated"):
        try:
            triage_summary = get_triage_service().triage_run(
                user_id=CI_SERVICE_USER_ID, run_id=result["run_id"]
            )
        except Exception:  # noqa: BLE001 — el triaje degrada; la ingesta ya está commiteada
            logger.exception("triage failed for run %s", result["run_id"])
    return CiWebhookResponse(**result, triage=triage_summary)


@router.get("/triage/run/{run_id}", response_model=List[TriageVerdictResponse])
def triage_run_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> List[TriageVerdictResponse]:
    try:
        verdicts = repo.get_triage_for_run(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [TriageVerdictResponse(**v) for v in verdicts]


@router.post("/triage/run/{run_id}/resolve")
def resolve_triage_run_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: TriageService = Depends(get_triage_service),
) -> Dict[str, int]:
    try:
        return service.resolve_tiebreaks(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


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


@router.post("/integrations/github", response_model=GitHubConfigResponse)
def set_github_integration(
    body: GitHubConfigRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> GitHubConfigResponse:
    try:
        integrations.upsert_github_config(
            user_id=user.user_id, org_id=body.org_id,
            installation_id=body.installation_id, repo_full_name=body.repo_full_name,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return GitHubConfigResponse(configured=True, repo_full_name=body.repo_full_name,
                                installation_id=body.installation_id)


@router.get("/integrations/github", response_model=GitHubConfigResponse)
def get_github_integration(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> GitHubConfigResponse:
    try:
        cfg = integrations.get_github_config(user_id=user.user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return GitHubConfigResponse(**cfg)


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


@router.patch("/defects/{family_id}/label", response_model=FamilyLabelResponse)
def set_family_label_v2(
    family_id: str,
    body: SetFamilyLabelRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> FamilyLabelResponse:
    try:
        ok = repo.set_family_label(user_id=user.user_id, family_id=family_id,
                                   label=body.label, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if not ok:
        raise HTTPException(status_code=404, detail="defect family not found")
    return FamilyLabelResponse(family_id=family_id, label=body.label)


@router.get("/calibration/metrics", response_model=CalibrationMetricsResponse)
def calibration_metrics_v2(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> CalibrationMetricsResponse:
    try:
        metrics = repo.get_calibration_metrics(user_id=user.user_id, org_id=org_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if metrics is None:
        raise HTTPException(status_code=404, detail="org not found or not a member")
    return CalibrationMetricsResponse(**metrics)


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
        text = (analyzer.analyze(data["family"], data["failures"]) or "")[:8000]
        if not text.strip():
            raise HTTPException(status_code=503, detail="el análisis IA no produjo resultado")
        repo.save_root_cause(user_id=user.user_id, defect_id=defect_id, text=text)
        return RootCauseResponse(defect_id=defect_id, root_cause=text, cached=False)
    except HTTPException:
        raise
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001 — fallo del LLM/proveedor
        logger.exception("root-cause analysis failed for defect %s", defect_id)
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


@router.post("/actions/run/{run_id}/propose", response_model=ProposeActionsResponse)
def propose_actions_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> ProposeActionsResponse:
    try:
        return ProposeActionsResponse(**service.propose_actions(user_id=user.user_id, run_id=run_id))
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.get("/actions", response_model=List[ActionResponse])
def list_actions_v2(
    org_id: str,
    status: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: ActionRepository = Depends(get_action_repo),
) -> List[ActionResponse]:
    if status is not None and status not in _ACTION_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    try:
        rows = repo.get_actions(user_id=user.user_id, org_id=org_id, status=status)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [ActionResponse(**r) for r in rows]


@router.post("/actions/{action_id}/approve", response_model=ActionApproveResponse)
def approve_action_v2(
    action_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> ActionApproveResponse:
    try:
        return ActionApproveResponse(
            **service.approve_action(user_id=user.user_id, action_id=action_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=503, detail="GitHub App no configurada") from exc
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail="GitHub API error") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/actions/{action_id}/reject", response_model=ActionRejectResponse)
def reject_action_v2(
    action_id: str,
    body: ActionRejectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> ActionRejectResponse:
    try:
        ok = service.reject_action(user_id=user.user_id, action_id=action_id, reason=body.reason)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return ActionRejectResponse(rejected=ok)


@router.post("/certificates/run/{run_id}", response_model=CertificateResponse)
def generate_certificate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        return CertificateResponse(**service.generate(user_id=user.user_id, run_id=run_id,
                                                      created_at=created_at))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SigningKeyMissing as exc:
        raise HTTPException(status_code=503, detail="Firma no configurada") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.get("/certificates/{run_id}/html", response_class=HTMLResponse)
def get_certificate_html_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> HTMLResponse:
    try:
        cert = service.get(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if cert is None:
        raise HTTPException(status_code=404, detail="certificate not found")
    return HTMLResponse(render_html(cert["canonical_json"], cert["signature"]))


@router.get("/certificates/{run_id}", response_model=CertificateResponse)
def get_certificate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    try:
        cert = service.get(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if cert is None:
        raise HTTPException(status_code=404, detail="certificate not found")
    return CertificateResponse(run_id=cert["run_id"], verdict=cert["verdict"],
                               risk_score=cert["risk_score"], canonical_json=cert["canonical_json"],
                               signature=cert["signature"], created_at=cert["created_at"])


@router.post("/certificates/verify", response_model=CertificateVerifyResponse)
def verify_certificate_v2(
    body: CertificateVerifyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateVerifyResponse:
    try:
        valido = service.verify_payload(cert=body.canonical_json, signature=body.signature)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return CertificateVerifyResponse(valido=valido)


@router.post("/gate/run/{run_id}", response_model=GateResponse)
def publish_gate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: GateService = Depends(get_gate_service),
) -> GateResponse:
    try:
        return GateResponse(**service.publish(user_id=user.user_id, run_id=run_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=503, detail="GitHub App no configurada") from exc
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail="GitHub API error") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
