import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import psycopg
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.defects.embedder import LocalEmbedder

from src.certify.gate import GateService
from src.certify.repository import CertificateRepository
from src.certify.render import render_html, render_pdf
from src.certify.service import CertificateService, parse_public_keys
from src.certify.signing import SigningKeyMissing, canonical_json, verify
from src.db.pool import get_pool
from src.config import (CI_MAX_BODY_BYTES, CI_SERVICE_ORG_ID, CI_SERVICE_USER_ID,
                        CI_WEBHOOK_SECRET, GITHUB_APP_CLIENT_ID, GITHUB_APP_CLIENT_SECRET,
                        GITHUB_APP_SLUG, INGEST_MAX_BYTES, LLM_MODEL,
                        MNEMO_PUBLIC_APP_URL, MNEMO_SIGNING_PRIVATE_KEY,
                        MNEMO_SIGNING_PUBLIC_KEY, MNEMO_SIGNING_RETIRED_PUBLIC_KEYS,
                        MNEMO_VERSION, multi_tenant_enabled)
from src.actions.ai_repair import AIRepairActuator
from src.actions.quarantine import QuarantineActuator
from src.actions.repository import ActionRepository
from src.actions.selfheal.selfheal import SelfHealActuator
from src.actions.service import ActionService
from src.actions.ticket import TicketActuator
from src.ci.github_app import GitHubCodeHost, GitHubError
from src.ci.github_auth import GitHubAppAuth, GitHubAppNotConfigured, GitHubAuthError
from src.ci.ingest_fields import (PROJECT_MAX_LEN, optional_text, parse_branch,
                                  parse_commit_sha)
from src.ci.github_install_proof import (GitHubProofNotConfigured, GitHubUserInstallationVerifier,
                                         InvalidInstallState, sign_install_state,
                                         verify_install_state)
from src.ci.ingestion_service import CiIngestionService
from src.triage.service import TriageService
from src.ci.models import CiRunArtifact
from src.ci.webhook_auth import verify_signature
from src.defects.ingestion_service import IngestionService
from src.defects.repository import AssuranceRepository
from src.assurance.narrator import LLMNarrator, Narrator
from src.llm.factory import get_llm_provider, llm_status, resolved_model_name
from src.llm.org_policy import bind_llm_org, bind_llm_org_of, external_llm_allowed
from src.assurance.verdict import build_verdict
from src.jira.client import JiraApiError
from src.jira.integrations_repository import InstallationAlreadyBound, IntegrationsRepository
from src.jira.ingestion_service import JiraIngestionService
from src.jira.safe_url import validate_base_url
from src.graph.service import GraphService
from src.graph.gaps import detect_gaps
from src.ci.ingest_tokens import IngestTokenRepository
from src.continuity.index import compute_index, list_projects
from src.continuity.repository import ContinuityRepository
from src.continuity.service import ContinuityService
from src.knowledge.repository import QaKnowledgeRepository
from src.knowledge.service import KnowledgeService
from src.memory.family_memory import memory_payload, memory_summary_payload
from src.memory.repository import FamilyMemoryRepository
from src.knowledge.proposal_repository import KnowledgeProposalRepository
from src.knowledge.proposal_service import KnowledgeProposalService
from src.knowledge.import_service import (
    ImportNotConfigured,
    ImportRateLimited,
    KnowledgeImportService,
)
from src.multitenant_models import (
    ActionApproveResponse,
    ActionRejectRequest,
    ActionRejectResponse,
    ActionResponse,
    AutomationGenerateRequest,
    AutomationPrRequest,
    AskRequest,
    AskResponse,
    AssuranceVerdictResponse,
    BriefingResponse,
    CalibrationMetricsResponse,
    CertificateResponse,
    CertificateVerifyRequest,
    CertificateVerifyResponse,
    FamilyLabelResponse,
    GateResponse,
    CiWebhookResponse,
    CreateOrgRequest,
    HandoverEmitRequest,
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
    IngestTokenCreateRequest,
    KnowledgeAskRequest,
    KnowledgeCreateRequest,
    KnowledgeImportRequest,
    KnowledgeImportResponse,
    KnowledgeProposalApproveRequest,
    KnowledgeProposalGenerateRequest,
    KnowledgeProposalRejectRequest,
    KnowledgeUpdateRequest,
    KnowledgeSearchRequest,
    OnboardingRequest,
    OrganizationResponse,
    ProposeActionsResponse,
    RepoIndexRequest,
    RootCauseResponse,
    SetFamilyLabelRequest,
    TestPlanGenerateRequest,
    TestPlanXrayExportRequest,
    TriageVerdictResponse,
)
from src.repo_ingest.service import index_repo_tests
from src.repo_ingest.repository import TestAssetRepository
from src.automation.agent import generate_playwright_test, _case_text
from src.automation.style import retrieve_style_examples
from src.onboarding.agent import summarize_domain, learning_path
from src.testplan.agent import generate_test_plan
from src.testplan.ingest import resolve_hu_from_upload
from src.testplan.jira_source import hu_text_from_jira
from src.xray.client import XrayClient, XrayImportError, XrayNotConfigured
from src.xray.config import XrayConfig
from src.security import AuthenticatedUser, get_current_user
from src.orgs.repository import OrganizationRepository
from src.orgs.access import OrgAccess, Resource, enforce, get_org_access
from src.orgs.permissions import Capability

router = APIRouter(prefix="/v2", tags=["v2"])

_ACTION_STATUSES = {"proposed", "approved", "rejected", "materialized", "materializing"}

# Singletons perezosos (sin anotacion PEP 604 para compatibilidad <3.10)
_repo = None
_assurance_repo = None
_family_memory_repo = None
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
_continuity_service = None
_gate_service = None
_embedder = None
_knowledge_repo = None
_knowledge_proposal_repo = None
_knowledge_proposal_service = None
_ingest_token_repo = None


def get_repo() -> OrganizationRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _repo
    if _repo is None:
        _repo = OrganizationRepository()
    return _repo


def get_family_memory_repo() -> FamilyMemoryRepository:
    global _family_memory_repo
    if _family_memory_repo is None:
        _family_memory_repo = FamilyMemoryRepository()
    return _family_memory_repo


def _run_memory(user_id: str, run_id: Optional[str], *,
                detail: bool = False) -> Optional[Dict[str, Any]]:
    """Bloque `memory` de la respuesta de ingesta. Best-effort y solo presentación.

    `detail=True` (subida web: una persona miembro) trae razones y lecciones. Por token
    de ingesta o webhook, solo el resumen: un token no es un miembro y el log del CI
    puede ser público."""
    if not run_id or not multi_tenant_enabled():
        return None
    try:
        memories = get_family_memory_repo().for_run(user_id=user_id, run_id=run_id)
        if detail:
            return memory_payload(memories)
        return memory_summary_payload(memories, app_url=MNEMO_PUBLIC_APP_URL)
    except Exception:  # noqa: BLE001 — la ingesta ya está hecha; la memoria es un extra
        logger.exception("memoria del run %s no disponible", run_id)
        return None


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
        _ingestion_service = IngestionService(repo=get_assurance_repo(), embedder=get_embedder())
    return _ingestion_service


def get_narrator() -> Narrator:
    global _narrator
    if _narrator is None:
        # Cacheada por versión de datos del veredicto: el GET del run no llama al LLM
        # en cada carga (auditoría 2026-11-23, 03-tecnica E8).
        from src.assurance.narrator_cache import CachingNarrator
        _narrator = CachingNarrator(LLMNarrator(_llm_provider_or_none()))
    return _narrator


def _llm_provider_or_none():
    """El proveedor LLM, o None si no se puede construir (sin configurar, falta la
    clave…). Las dependencias que lo envuelven degradan: un LLM mal configurado no
    puede tumbar con un 500 un endpoint cuya parte de IA es opcional."""
    from src.llm.factory import get_llm_provider
    try:
        return get_llm_provider()
    except Exception as exc:  # noqa: BLE001 — se degrada, pero se deja rastro
        logger.warning("LLM no disponible, se degrada: %s", exc)
        return None


def get_root_cause_analyzer():
    global _root_cause_analyzer
    if _root_cause_analyzer is None:
        from src.assurance.root_cause import RootCauseAnalyzer
        _root_cause_analyzer = RootCauseAnalyzer(_llm_provider_or_none())
    return _root_cause_analyzer


def get_integrations_repo() -> IntegrationsRepository:
    global _integrations_repo
    if _integrations_repo is None:
        _integrations_repo = IntegrationsRepository()
    return _integrations_repo


def get_jira_ingestion_service() -> JiraIngestionService:
    global _jira_service
    if _jira_service is None:
        _jira_service = JiraIngestionService(
            repo=get_assurance_repo(), embedder=get_embedder(),
            integrations=get_integrations_repo(),
        )
    return _jira_service


def get_ci_ingestion_service() -> CiIngestionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _ci_ingestion_service
    if _ci_ingestion_service is None:
        _ci_ingestion_service = CiIngestionService(
            repo=get_assurance_repo(), embedder=get_embedder()
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


def get_github_app_auth() -> GitHubAppAuth:
    """Dependencia inyectable (override en tests) para verificar instalaciones."""
    return _get_github_auth()


def get_github_user_verifier() -> GitHubUserInstallationVerifier:
    """Dependencia inyectable (override en tests): canjea el `code` OAuth del callback
    de la GitHub App y comprueba GET /user/installations."""
    return GitHubUserInstallationVerifier(client_id=GITHUB_APP_CLIENT_ID,
                                          client_secret=GITHUB_APP_CLIENT_SECRET)


def _verify_installation_possession(
    verifier: GitHubUserInstallationVerifier, *, body: GitHubConfigRequest, user_id: str
) -> None:
    """Prueba de posesión de la instalación (auditoría 23-nov, H4; ver
    src/ci/github_install_proof.py). Sin ella, el primero que reclamaba un
    installation_id ajeno se lo quedaba. En self-host single-tenant no aplica: no hay
    otros tenants a los que suplantar. Va ANTES del upsert: quien no demuestra acceso
    tampoco aprende (409) si la instalación ya está vinculada a otra org."""
    if not multi_tenant_enabled():
        return
    if not body.state or not body.code:
        raise HTTPException(
            status_code=400,
            detail="Falta la prueba de posesión (state y code): inicia la vinculación "
                   "desde GET /v2/integrations/github/install-url")
    try:
        verify_install_state(body.state, org_id=body.org_id, user_id=user_id)
    except InvalidInstallState as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except GitHubProofNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not verifier.configured:
        raise HTTPException(status_code=503,
                            detail="OAuth de la GitHub App no configurado; no se puede "
                                   "verificar el acceso a la instalación")
    try:
        has_access = verifier.user_has_installation(code=body.code,
                                                    installation_id=body.installation_id)
    except (GitHubAuthError, GitHubProofNotConfigured) as exc:
        raise HTTPException(status_code=403,
                            detail="No se pudo verificar tu acceso a la instalación de GitHub") from exc
    if not has_access:
        raise HTTPException(status_code=403,
                            detail="Tu usuario de GitHub no tiene acceso a esa instalación")


def _verify_installation_ownership(
    auth: GitHubAppAuth, *, installation_id: str, repo_full_name: str
) -> None:
    """Verifica, al vincular GitHub, que la instalación reclamada es del cliente.

    Mitiga N-C1 (confused-deputy): sin esto un admin podía apuntar al
    installation_id de otro tenant. Comprueba que la cuenta dueña de la
    instalación coincide con el owner del repo. Si la App no está configurada,
    en multi-tenant se rechaza (no se puede verificar); en self-host se permite.
    """
    owner = repo_full_name.split("/", 1)[0]
    try:
        account = auth.installation_account(installation_id)
    except GitHubAppNotConfigured as exc:
        if multi_tenant_enabled():
            raise HTTPException(
                status_code=503,
                detail="GitHub App no configurada; no se puede verificar la instalación",
            ) from exc
        return  # self-host single-tenant: se degrada permitiendo el bind
    except GitHubAuthError as exc:
        raise HTTPException(
            status_code=403, detail="No se pudo verificar la instalación de GitHub"
        ) from exc
    if account.lower() != owner.lower():
        raise HTTPException(
            status_code=403,
            detail="El repositorio no pertenece a la cuenta de la instalación de GitHub",
        )


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

    def analyze(self, family, failures, **kwargs):
        return get_root_cause_analyzer().analyze(family, failures, **kwargs)


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
        try:
            _ai_repair_provider = get_llm_provider()
        except Exception:
            _ai_repair_provider = None
        _action_service = ActionService(
            repo=get_assurance_repo(),
            actions_repo=get_action_repo(),
            actuators={
                "flaky": QuarantineActuator(),
                "real": TicketActuator(_LazyRootCauseAnalyzer()),
                "maintenance": SelfHealActuator(explainer=_LazySelfHealExplainer()),
            },
            codehost_factory=_github_codehost_factory,
            ai_repair=AIRepairActuator(_ai_repair_provider),
            memory_fn=get_family_memory_repo().load,
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
        try:
            _llm = get_llm_provider()
        except Exception:
            _llm = None
        _certificate_service = CertificateService(
            repo=get_assurance_repo(), cert_repo=get_certificate_repo(),
            private_key=MNEMO_SIGNING_PRIVATE_KEY, public_key=MNEMO_SIGNING_PUBLIC_KEY,
            mnemo_version=MNEMO_VERSION, model_version=LLM_MODEL or "unknown",
            llm_provider=_llm,
            retired_public_keys=parse_public_keys(MNEMO_SIGNING_RETIRED_PUBLIC_KEYS),
        )
    return _certificate_service


def get_continuity_service() -> ContinuityService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _continuity_service
    if _continuity_service is None:
        _continuity_service = ContinuityService(
            repo=ContinuityRepository(),
            private_key=MNEMO_SIGNING_PRIVATE_KEY, public_key=MNEMO_SIGNING_PUBLIC_KEY,
            mnemo_version=MNEMO_VERSION,
        )
    return _continuity_service


def get_gate_service() -> GateService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _gate_service
    if _gate_service is None:
        _gate_service = GateService(repo=get_assurance_repo(), cert_repo=get_certificate_repo(),
                                    codehost_factory=_github_codehost_factory,
                                    memory_fn=get_family_memory_repo().load,
                                    app_url=MNEMO_PUBLIC_APP_URL)
    return _gate_service


def get_embedder():
    # Un único embedder (y un único modelo en RAM) por proceso, compartido por todos
    # los servicios y repositorios (auditoría 2026-11-23 #13).
    from src.defects.embedder import get_shared_embedder
    global _embedder
    if _embedder is None:
        _embedder = get_shared_embedder()
    return _embedder


def get_knowledge_repo() -> QaKnowledgeRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _knowledge_repo
    if _knowledge_repo is None:
        _knowledge_repo = QaKnowledgeRepository(embedder=get_embedder())
    return _knowledge_repo


def get_knowledge_proposal_repo() -> KnowledgeProposalRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _knowledge_proposal_repo
    if _knowledge_proposal_repo is None:
        _knowledge_proposal_repo = KnowledgeProposalRepository(embedder=get_embedder())
    return _knowledge_proposal_repo


def get_knowledge_proposal_service() -> KnowledgeProposalService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _knowledge_proposal_service
    if _knowledge_proposal_service is None:
        _knowledge_proposal_service = KnowledgeProposalService(
            repo=get_knowledge_proposal_repo(),
            assurance_repo=get_assurance_repo(),
            analyzer=get_root_cause_analyzer(),
        )
    return _knowledge_proposal_service


def get_ingest_token_repo() -> IngestTokenRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _ingest_token_repo
    if _ingest_token_repo is None:
        _ingest_token_repo = IngestTokenRepository()
    return _ingest_token_repo


def get_knowledge_proposal_service_optional() -> Optional[KnowledgeProposalService]:
    """Variante para hooks best-effort (p. ej. causa-raíz→propuesta): None en vez de
    503 cuando el multi-tenant no está configurado, para no romper el endpoint anfitrión."""
    try:
        return get_knowledge_proposal_service()
    except HTTPException:
        return None


_knowledge_import_service = None


def get_knowledge_import_service() -> KnowledgeImportService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _knowledge_import_service
    if _knowledge_import_service is None:
        _knowledge_import_service = KnowledgeImportService(
            repo=get_knowledge_proposal_repo(),
            integrations=IntegrationsRepository(),
        )
    return _knowledge_import_service


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _org_to_response(org: Dict[str, Any]) -> OrganizationResponse:
    return OrganizationResponse(
        id=str(org["id"]),
        name=org["name"],
        join_code=org.get("join_code"),
        join_code_expires_at=_iso_or_none(org.get("join_code_expires_at")),
        role=org.get("role"),
        created_at=str(org["created_at"]) if org.get("created_at") is not None else None,
    )


@router.get("/orgs", response_model=List[OrganizationResponse])
def list_orgs(
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrganizationRepository = Depends(get_repo),
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
    repo: OrganizationRepository = Depends(get_repo),
) -> OrganizationResponse:
    try:
        org = repo.create_organization(user_id=user.user_id, name=req.name)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if org is None:
        raise HTTPException(status_code=502, detail="Organization could not be created")
    return _org_to_response(org)


# Freno a la fuerza bruta del código de unión (10 hex = 40 bits): fallos por USUARIO
# autenticado y no por IP (todo el tráfico del navegador llega por el proxy de
# Vercel). En memoria del proceso: el backend corre con un solo worker.
_JOIN_MAX_FAILURES = 10
_JOIN_WINDOW_SECONDS = 3600
_join_failures: Dict[str, List[float]] = {}
from time import monotonic as _join_clock  # noqa: E402 — junto a su único uso


def _recent_join_failures(user_id: str) -> List[float]:
    now = _join_clock()
    recent = [t for t in _join_failures.get(user_id, []) if now - t < _JOIN_WINDOW_SECONDS]
    _join_failures[user_id] = recent
    return recent


@router.post("/orgs/join", response_model=OrganizationResponse)
def join_org(
    req: JoinOrgRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: OrganizationRepository = Depends(get_repo),
) -> OrganizationResponse:
    if len(_recent_join_failures(user.user_id)) >= _JOIN_MAX_FAILURES:
        raise HTTPException(status_code=429,
                            detail="Demasiados códigos incorrectos. Inténtalo dentro de una hora.")
    try:
        org = repo.join_organization(user_id=user.user_id, join_code=req.join_code)
    except ValueError as exc:
        _join_failures[user.user_id] = [*_recent_join_failures(user.user_id), _join_clock()]
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if org is None:
        raise HTTPException(status_code=502, detail="Joined organization could not be loaded")
    return _org_to_response(org)


# `?probe=1` es público y hace una llamada REAL al LLM: sin freno, un bucle de
# peticiones vaciaba la cuota (el free tier de la demo). El resultado del probe se
# reutiliza durante la ventana; el keep-warm no usa probe y no se ve afectado.
_PROBE_TTL_SECONDS = 60
_probe_cache: Optional[Tuple[float, Dict[str, Any]]] = None
_monotonic = time.monotonic


def _llm_status_for_health(probe: bool) -> Dict[str, Any]:
    global _probe_cache
    if not probe:
        return llm_status(probe=False)
    now = _monotonic()
    if _probe_cache is not None and now - _probe_cache[0] < _PROBE_TTL_SECONDS:
        return _probe_cache[1]
    status = llm_status(probe=True)
    _probe_cache = (now, status)
    return status


# /health comprueba la BD (auditoría 2026-11-23 #20): antes respondía "active" sin
# tocarla y el keep-warm salía verde con la BD caída. Timeout corto: es un ping.
HEALTH_DB_TIMEOUT_SECONDS = 3
_HEALTH_DB_STATEMENT_TIMEOUT_MS = HEALTH_DB_TIMEOUT_SECONDS * 1000


def _database_configured() -> bool:
    from src import config
    return bool(config.DATABASE_URL)


def _ping_database() -> None:
    """`select 1` por el pool con timeout corto; lanza si la BD no responde."""
    with get_pool().connection(timeout=HEALTH_DB_TIMEOUT_SECONDS) as conn:
        conn.execute(f"set local statement_timeout = {_HEALTH_DB_STATEMENT_TIMEOUT_MS}")
        conn.execute("select 1")


def _db_status_for_health() -> str:
    if not _database_configured():
        return "not_configured"
    try:
        _ping_database()
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de BD = no listo
        # Al log solo el tipo: el mensaje del driver puede llevar el DSN.
        logger.error("health: la BD no responde (%s)", type(exc).__name__)
        return "error"
    return "ok"


@router.get("/health/live")
def health_live_v2() -> Dict[str, str]:
    """Liveness ligera (HEALTHCHECK del contenedor/Render): el proceso responde. No
    toca BD ni LLM, para que una BD caída no haga reiniciar el contenedor en bucle."""
    return {"status": "alive"}


@router.get("/health")
def health_v2(response: Response, probe: bool = False) -> Dict[str, Any]:
    # `?probe=1` hace una llamada mínima real al LLM (como mucho una por ventana) y
    # reporta el error crudo (401/429/timeout). Sin probe solo valida la config.
    db = _db_status_for_health()
    if db == "error":
        response.status_code = 503
    return {"status": "degraded" if db == "error" else "active",
            "model": resolved_model_name(),
            "llm": _llm_status_for_health(probe),
            "db": db,
            "multi_tenant_enabled": multi_tenant_enabled()}


def _read_upload_capped(file: UploadFile) -> bytes:
    """Lee una subida acotada a INGEST_MAX_BYTES (anti-DoS por archivo enorme).
    Lee 1 byte de más para detectar el exceso sin cargar todo en memoria."""
    data = file.file.read(INGEST_MAX_BYTES + 1)
    if len(data) > INGEST_MAX_BYTES:
        raise HTTPException(status_code=413, detail="archivo demasiado grande")
    return data


async def _read_upload_capped_async(file: UploadFile) -> bytes:
    data = await file.read(INGEST_MAX_BYTES + 1)
    if len(data) > INGEST_MAX_BYTES:
        raise HTTPException(status_code=413, detail="archivo demasiado grande")
    return data


_MULTIPART_MARGIN_BYTES = 65536  # cabeceras/boundaries del multipart sobre el archivo


def _reject_declared_oversize(request: Request) -> None:
    """413 por `Content-Length` ANTES de leer el cuerpo (margen para el multipart)."""
    declared = request.headers.get("content-length")
    if (declared is not None and declared.isdigit()
            and int(declared) > INGEST_MAX_BYTES + _MULTIPART_MARGIN_BYTES):
        raise HTTPException(status_code=413, detail="payload too large")


def _pipeline_pending(user_id: str, result: Dict[str, Any]) -> bool:
    """¿Hay que correr triaje + acta + gate tras esta ingesta?

    Siempre si el run es nuevo. Si llegó deduplicado, solo si se quedó sin
    triaje o sin acta (el pipeline es best-effort: un fallo dejaba el run cojo para
    siempre porque el reintento del CI solo devolvía «deduplicado»)."""
    if not result.get("deduplicated"):
        return True
    try:
        return get_assurance_repo().run_needs_pipeline(user_id=user_id,
                                                       run_id=result["run_id"])
    except Exception:  # noqa: BLE001 — sin poder comprobarlo, no relanzar (como antes)
        logger.exception("no se pudo comprobar el pipeline del run %s", result.get("run_id"))
        return False


def _ingest_and_run_pipeline(service: IngestionService, *, user_id: str, org_id: str,
                             project: str, source: str, data: bytes,
                             commit_sha: Optional[str] = None,
                             branch: Optional[str] = None,
                             memory_detail: bool = False) -> Dict[str, Any]:
    """Ingesta del report + pipeline post-ingesta. Bloqueante (embeddings, BD, LLM):
    llamar SIEMPRE desde el threadpool. Compartido por la subida web y /ci/ingest."""
    result = service.ingest_report(user_id=user_id, org_id=org_id, project=project,
                                   source=source, data=data, commit_sha=commit_sha,
                                   branch=branch)
    triage, verdict, gate = None, None, None
    if _pipeline_pending(user_id, result):
        triage, verdict, gate = _post_ingest_pipeline(user_id, result["run_id"])
    return {**result, "triage": triage, "verdict": verdict, "gate": gate,
            "memory": _run_memory(user_id, result.get("run_id"), detail=memory_detail)}


async def _ingest_report_off_loop(service: IngestionService, **kwargs) -> Dict[str, Any]:
    """Corre la ingesta + pipeline en el threadpool y traduce los errores a HTTP."""
    try:
        return await run_in_threadpool(_ingest_and_run_pipeline, service, **kwargs)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/ingest/report", response_model=IngestReportResponse)
async def ingest_report_v2(
    request: Request,
    background: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestReportResponse:
    """Subida de un report desde la web: ingesta + triaje + acta + gate (como
    /ci/ingest) y propuestas de conocimiento tras responder.

    El multipart se parsea a mano: con `UploadFile = File(...)` en la firma, FastAPI
    lee el cuerpo ANTES de autenticar. Orden: auth (JWT) → cota → campos →
    membresía → lectura del archivo → parseo/embeddings (en el threadpool)."""
    _reject_declared_oversize(request)
    form = await request.form()
    upload = form.get("file")
    project = form.get("project")
    org_id = form.get("org_id")
    source = str(form.get("source") or "auto")
    if (upload is None or isinstance(upload, str) or not isinstance(project, str)
            or not project or not isinstance(org_id, str) or not org_id):
        raise HTTPException(status_code=422,
                            detail="faltan los campos multipart: file, project y org_id")
    if len(project) > PROJECT_MAX_LEN:
        raise HTTPException(status_code=400,
                            detail=f"project demasiado largo (máx. {PROJECT_MAX_LEN})")
    # Membresía Y rol (un viewer no sube runs) antes de leer el archivo.
    await run_in_threadpool(enforce, access, user.user_id, Capability.QA_WORK, org_id=org_id)
    data = await _read_upload_capped_async(upload)
    result = await _ingest_report_off_loop(service, user_id=user.user_id, org_id=org_id,
                                           project=project, source=source, data=data,
                                           memory_detail=True)
    if not result.get("deduplicated"):
        background.add_task(_propose_knowledge_after_ingest, user.user_id, org_id)
    return IngestReportResponse(**result)


def _post_ingest_pipeline(user_id: str, run_id: str):
    """Triaje + certificado + gate tras una ingesta, todo best-effort (cada paso
    degrada sin romper lo ya commiteado). Compartido por el webhook de CI y por
    la ingesta genérica por token (/ci/ingest). Devuelve (triage, verdict, gate)."""
    bind_llm_org_of("test_runs", run_id)
    triage_summary = None
    try:
        triage_summary = get_triage_service().triage_run(user_id=user_id, run_id=run_id)
    except Exception:  # noqa: BLE001 — el triaje degrada; la ingesta ya está commiteada
        logger.exception("triage failed for run %s", run_id)
    verdict = None
    gate = None
    if triage_summary is not None:
        try:
            created_at = datetime.now(timezone.utc).isoformat()
            cert = get_certificate_service().generate(
                user_id=user_id, run_id=run_id, created_at=created_at)
            verdict = cert.get("verdict")
        except Exception:  # noqa: BLE001 — el cert degrada; la ingesta/triaje ya están commiteados
            logger.exception("certificate failed for run %s", run_id)
        try:
            gate_res = get_gate_service().publish(user_id=user_id, run_id=run_id)
            gate = gate_res.get("conclusion")
        except Exception:  # noqa: BLE001 — el gate degrada (p.ej. sin GitHub App)
            logger.exception("gate failed for run %s", run_id)
    return triage_summary, verdict, gate


_PROPOSAL_CAP_POST_INGEST = 3  # familias por ingesta: acota las llamadas LLM del lote


def _propose_knowledge_after_ingest(user_id: str, org_id: str) -> None:
    """Deja propuestas de conocimiento en la bandeja tras una ingesta. Best-effort.

    Corre como BackgroundTask: FastAPI la ejecuta DESPUÉS de enviar la respuesta, así
    que el CI no espera al LLM. Cierra el lazo que hasta ahora exigía pulsar un botón
    por familia (auditoría 12-ago, H4a).

    Si el proceso muere a mitad no se corrompe nada: generate commitea por familia y
    las que se queden sin propuesta siguen siendo candidatas en la próxima ingesta.
    """
    try:
        bind_llm_org(org_id)
        service = get_knowledge_proposal_service_optional()
        if service is None:
            return  # multi-tenant no configurado: nada que hacer
        if not external_llm_allowed(org_id):
            logger.info("propuestas post-ingesta omitidas: LLM externo desactivado por la org")
            return
        if not llm_status().get("configured"):
            # Sin LLM no hay causa raíz: generate gastaría el lote en fallbacks que
            # luego descarta, en CADA run. llm_status() sin probe NO llama a la API.
            logger.info("propuestas post-ingesta omitidas: LLM no configurado")
            return
        out = service.generate(user_id=user_id, org_id=org_id,
                               cap=_PROPOSAL_CAP_POST_INGEST)
        # El conteo en el log delata una configuración mala (0 candidatas siempre)
        # en vez de fallar en silencio.
        logger.info("propuestas post-ingesta org=%s: %s", org_id, out)
    except Exception:  # noqa: BLE001 — best-effort: la ingesta ya está commiteada
        logger.exception("propuestas post-ingesta fallaron para org %s", org_id)


def _process_ci_artifact(artifact: CiRunArtifact) -> CiWebhookResponse:
    """Pipeline post-validación del webhook: ingesta + triaje + certificado + gate.

    Es CPU (embeddings torch) e I/O bloqueante (Postgres, LLM, GitHub API). Se
    ejecuta en el threadpool (ver `ci_webhook`) para no congelar el event loop
    del único proceso y bloquear al resto de tenants mientras se procesa un run.
    """
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
    verdict = None
    gate = None
    if _pipeline_pending(CI_SERVICE_USER_ID, result):
        triage_summary, verdict, gate = _post_ingest_pipeline(
            CI_SERVICE_USER_ID, result["run_id"])
    return CiWebhookResponse(**result, triage=triage_summary, verdict=verdict, gate=gate,
                             memory=_run_memory(CI_SERVICE_USER_ID, result.get("run_id")))


async def _read_body_capped(request: Request, cap: int) -> bytes:
    """Lee el cuerpo por trozos cortando en cuanto supera `cap`: sin Content-Length
    (Transfer-Encoding: chunked) `request.body()` lo leería entero antes de mirar."""
    chunks: List[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:
            raise HTTPException(status_code=413, detail="payload too large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/ci/webhook", response_model=CiWebhookResponse)
async def ci_webhook(request: Request, background: BackgroundTasks) -> CiWebhookResponse:
    if not CI_SERVICE_ORG_ID:
        # Sin org fija, el org_id saldría del CUERPO: quien tenga el secreto compartido
        # podría inyectar runs (y autoemitir actas) en otra org donde la cuenta de
        # servicio sea miembro. Se rechaza sin leer el cuerpo (auditoría 23-nov, H6).
        raise HTTPException(
            status_code=503,
            detail="Webhook global desactivado: fija CI_SERVICE_ORG_ID, o usa la "
                   "ingesta por organización /v2/ci/ingest con un token de ingesta")
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > CI_MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    body = await _read_body_capped(request, CI_MAX_BODY_BYTES)
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, CI_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="invalid signature")
    if not CI_SERVICE_USER_ID:
        raise HTTPException(status_code=503, detail="CI service account not configured")
    try:
        artifact = CiRunArtifact.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid artifact") from exc
    if artifact.org_id != CI_SERVICE_ORG_ID:
        raise HTTPException(status_code=403, detail="org_id not allowed for this CI account")
    resp = await run_in_threadpool(_process_ci_artifact, artifact)
    if not resp.deduplicated:
        # Después de responder al CI: la generación llama al LLM y no debe entrar en
        # el tiempo de respuesta del webhook.
        background.add_task(_propose_knowledge_after_ingest,
                            CI_SERVICE_USER_ID, artifact.org_id)
    return resp


# ---------------------------------------------------------------------------
# Ingesta CI genérica por token — "cualquier CI se enchufa con un token"
# ---------------------------------------------------------------------------

@router.post("/ingest/tokens", response_model=Dict[str, Any])
def create_ingest_token(
    req: IngestTokenCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: IngestTokenRepository = Depends(get_ingest_token_repo),
) -> Dict[str, Any]:
    """Crea un token de ingesta (owner/admin). El token en claro SOLO viaja aquí."""
    enforce(access, user.user_id, Capability.ADMIN, org_id=req.org_id)
    try:
        out = repo.create_token(user_id=user.user_id, org_id=req.org_id, name=req.name)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if out is None:
        raise HTTPException(status_code=403, detail="requiere rol owner/admin en la organización")
    return out


@router.get("/ingest/tokens", response_model=List[Dict[str, Any]])
def list_ingest_tokens(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: IngestTokenRepository = Depends(get_ingest_token_repo),
) -> List[Dict[str, Any]]:
    try:
        return repo.list_tokens(user_id=user.user_id, org_id=org_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/ingest/tokens/{token_id}/revoke", response_model=Dict[str, bool])
def revoke_ingest_token(
    token_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: IngestTokenRepository = Depends(get_ingest_token_repo),
) -> Dict[str, bool]:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.INGEST_TOKEN, token_id))
    try:
        ok = repo.revoke_token(user_id=user.user_id, token_id=token_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if not ok:
        raise HTTPException(status_code=403,
                            detail="token no encontrado, ya revocado o sin permiso (owner/admin)")
    return {"revoked": True}


@router.post("/ci/ingest", response_model=Dict[str, Any])
async def ci_ingest(
    request: Request,
    background: BackgroundTasks,
    repo: IngestTokenRepository = Depends(get_ingest_token_repo),
    service: IngestionService = Depends(get_ingestion_service),
) -> Dict[str, Any]:
    """Ingesta CI genérica por TOKEN (sin sesión de usuario): sube el report de
    cualquiera de los 7 formatos soportados (autodetección) y corre el pipeline
    completo — ingesta + triaje + acta + gate (cada paso posterior best-effort).

        curl -H "Authorization: Bearer mnemo_it_…" \\
             -F file=@junit.xml -F project=mi-proyecto \\
             -F commit_sha=$GITHUB_SHA -F branch=$GITHUB_REF_NAME \\
             https://…/v2/ci/ingest

    `commit_sha` (hex 7-40) y `branch` son opcionales: con el commit, el gate puede
    publicar el check en el PR y el triaje detecta intermitencias en el mismo SHA.

    El multipart se parsea A MANO y DESPUÉS de autenticar + acotar el tamaño:
    con `file: UploadFile = File(...)` en la firma, FastAPI bufferiza el cuerpo
    completo ANTES de ejecutar la función — un anónimo podría hacernos volcar
    archivos enormes sin token (DoS). Orden: auth → cota → parseo.
    """
    # 1) Autenticación antes de tocar el cuerpo. Un token sin el prefijo
    #    mnemo_it_ se rechaza sin consultar la BD (resolve corta por formato).
    #    resolve hace un UPDATE en Postgres → threadpool, no en el event loop.
    auth = request.headers.get("Authorization", "")
    token = (auth[7:] if auth.startswith("Bearer ") else
             request.headers.get("X-Mnemo-Token", "")).strip()
    try:
        info = await run_in_threadpool(repo.resolve, token=token)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if info is None:
        raise HTTPException(status_code=401, detail="token de ingesta inválido o revocado")
    # El token autoriza por SU ORG; el pipeline corre con el actor que resolve
    # eligió (el creador si sigue siendo owner/admin, si no otro owner/admin).
    actor = info.get("acting_user_id")
    if not actor:
        raise HTTPException(status_code=403,
                            detail="la organización del token no tiene ningún owner/admin")
    # 2) Cota de tamaño antes de parsear (patrón de /ci/webhook; margen multipart)
    _reject_declared_oversize(request)
    # 3) Parseo del multipart (async; no bloquea el event loop)
    form = await request.form()
    upload = form.get("file")
    project = form.get("project")
    source = str(form.get("source") or "auto")
    if upload is None or isinstance(upload, str) or not project or not isinstance(project, str):
        raise HTTPException(status_code=422, detail="faltan los campos multipart: file y project")
    if len(project) > PROJECT_MAX_LEN:
        raise HTTPException(status_code=400,
                            detail=f"project demasiado largo (máx. {PROJECT_MAX_LEN})")
    try:
        commit_sha = parse_commit_sha(optional_text(form.get("commit_sha")))
        branch = parse_branch(optional_text(form.get("branch")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = await _read_upload_capped_async(upload)

    result = await _ingest_report_off_loop(
        service, user_id=actor, org_id=info["org_id"], project=project, source=source,
        data=data, commit_sha=commit_sha, branch=branch)
    if not result.get("deduplicated"):
        # Igual que en el webhook: tras responder, no dentro de la respuesta.
        background.add_task(_propose_knowledge_after_ingest, actor, info["org_id"])
    return result


@router.get("/runs", response_model=List[Dict[str, Any]])
def list_runs_v2(
    org_id: str,
    project: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> List[Dict[str, Any]]:
    """Histórico de runs navegable por proyecto/fecha (con veredicto del acta)."""
    try:
        return repo.list_runs(user_id=user.user_id, org_id=org_id, project=project,
                              limit=limit, offset=offset)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


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
    access: OrgAccess = Depends(get_org_access),
    service: TriageService = Depends(get_triage_service),
) -> Dict[str, int]:
    enforce(access, user.user_id, Capability.QA_WORK, resource=(Resource.RUN, run_id))
    bind_llm_org_of("test_runs", run_id)
    try:
        return service.resolve_tiebreaks(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/integrations/jira", response_model=JiraConfigResponse)
def set_jira_integration(
    body: JiraConfigRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> JiraConfigResponse:
    enforce(access, user.user_id, Capability.ADMIN, org_id=body.org_id)
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
    access: OrgAccess = Depends(get_org_access),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
    gh_auth: GitHubAppAuth = Depends(get_github_app_auth),
    verifier: GitHubUserInstallationVerifier = Depends(get_github_user_verifier),
) -> GitHubConfigResponse:
    enforce(access, user.user_id, Capability.ADMIN, org_id=body.org_id)
    _verify_installation_possession(verifier, body=body, user_id=user.user_id)
    _verify_installation_ownership(
        gh_auth, installation_id=body.installation_id, repo_full_name=body.repo_full_name
    )
    try:
        integrations.upsert_github_config(
            user_id=user.user_id, org_id=body.org_id,
            installation_id=body.installation_id, repo_full_name=body.repo_full_name,
        )
    except InstallationAlreadyBound as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return GitHubConfigResponse(configured=True, repo_full_name=body.repo_full_name,
                                installation_id=body.installation_id)


@router.get("/integrations/github/install-url", response_model=Dict[str, str])
def github_install_url(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, str]:
    """Inicio de la vinculación con prueba de posesión: devuelve la URL de instalación
    de la App y la de autorización OAuth, ambas con un `state` firmado para (org,
    usuario) que caduca en 10 min. GitHub redirige al callback con `installation_id`,
    `code` y `state`, que se mandan tal cual a POST /v2/integrations/github. El state
    no da permisos: el POST exige además owner/admin y el `code` de GitHub."""
    if not GITHUB_APP_SLUG or not GITHUB_APP_CLIENT_ID:
        raise HTTPException(status_code=503,
                            detail="GitHub App no configurada (GITHUB_APP_SLUG / GITHUB_APP_CLIENT_ID)")
    try:
        state = sign_install_state(org_id, user.user_id)
    except GitHubProofNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    query = urlencode({"state": state})
    return {
        "state": state,
        "install_url": f"https://github.com/apps/{GITHUB_APP_SLUG}/installations/new?{query}",
        "authorize_url": "https://github.com/login/oauth/authorize?"
                         + urlencode({"client_id": GITHUB_APP_CLIENT_ID, "state": state}),
    }


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
    access: OrgAccess = Depends(get_org_access),
    service: JiraIngestionService = Depends(get_jira_ingestion_service),
) -> JiraIngestResponse:
    enforce(access, user.user_id, Capability.QA_WORK, org_id=org_id)
    try:
        data = _read_upload_capped(file)
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
    access: OrgAccess = Depends(get_org_access),
    service: JiraIngestionService = Depends(get_jira_ingestion_service),
) -> JiraIngestResponse:
    enforce(access, user.user_id, Capability.QA_WORK, org_id=body.org_id)
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


_RELATED_K = 3


@router.get("/defects/{defect_id}/memory", response_model=Dict[str, Any])
def defect_memory_v2(
    defect_id: str,
    related: bool = True,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    memory_repo: FamilyMemoryRepository = Depends(get_family_memory_repo),
    krepo: QaKnowledgeRepository = Depends(get_knowledge_repo),
    arepo: AssuranceRepository = Depends(get_assurance_repo),
    embedder=Depends(get_embedder),
) -> Dict[str, Any]:
    """Lo que el equipo recuerda de una familia (panel de triaje): etiqueta y razón,
    lecciones, dónde más apareció y, bajo demanda, conocimiento relacionado."""
    try:
        uuid.UUID(defect_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="familia no encontrada") from None
    enforce(access, user.user_id, Capability.READ, resource=(Resource.FAMILY, defect_id))
    try:
        org_id = memory_repo.org_of_family(defect_id)
        found = memory_repo.load(user_id=user.user_id, org_id=org_id, family_ids=[defect_id]) \
            if org_id else []
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if not found:
        raise HTTPException(status_code=404, detail="familia no encontrada")
    memory = found[0]
    out = memory.to_dict(include_private=True)   # quien pide es miembro: email incluido
    out["related"] = _related_knowledge(user.user_id, org_id, memory, krepo, arepo,
                                        embedder) if related else []
    return out


def _related_knowledge(user_id, org_id, memory, krepo, arepo, embedder) -> List[Dict[str, Any]]:
    """Conocimiento parecido a la familia que NO está ya enlazado como lección.
    Best-effort: sin modelo o sin BD, el panel se muestra igual sin esta parte."""
    query = " ".join(x for x in (memory.title, memory.reason) if x)
    lesson_ids = {lesson.id for lesson in memory.lessons}
    try:
        hits = KnowledgeService(krepo, arepo, embedder=embedder).search_unified(
            user_id=user_id, org_id=org_id, query=query, k=_RELATED_K + len(lesson_ids))
    except Exception:  # noqa: BLE001
        logger.exception("conocimiento relacionado no disponible")
        return []
    return [{"id": h["id"], "title": h.get("title"), "score": h.get("score")}
            for h in hits if h.get("type") == "knowledge" and h["id"] not in lesson_ids
            ][:_RELATED_K]


def _embed_reason(embedder, reason: Optional[str]) -> Optional[List[float]]:
    """Vector de la razón del etiquetador, para que la búsqueda la encuentre por
    sí misma (auditoría 12-ago, H1). Best-effort: etiquetar es la acción y el
    vector un extra; si el modelo falla, la fila queda a NULL y el backfill de
    scripts/reembed.py la completa."""
    if not reason or not reason.strip():
        return None
    try:
        return embedder.embed(reason)
    except Exception:  # noqa: BLE001 — el modelo no puede tumbar el etiquetado
        logger.warning("no se pudo embeber la razón de la etiqueta", exc_info=True)
        return None


@router.patch("/defects/{family_id}/label", response_model=FamilyLabelResponse)
def set_family_label_v2(
    family_id: str,
    body: SetFamilyLabelRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    embedder=Depends(get_embedder),
) -> FamilyLabelResponse:
    enforce(access, user.user_id, Capability.QA_WORK, resource=(Resource.FAMILY, family_id))
    try:
        ok = repo.set_family_label(user_id=user.user_id, family_id=family_id,
                                   label=body.label, reason=body.reason,
                                   reason_embedding=_embed_reason(embedder, body.reason))
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
    access: OrgAccess = Depends(get_org_access),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    analyzer=Depends(get_root_cause_analyzer),
    proposals: Optional[KnowledgeProposalService] = Depends(get_knowledge_proposal_service_optional),
) -> RootCauseResponse:
    bind_llm_org_of("defect_families", defect_id)
    try:
        data = repo.get_family_with_failures(user_id=user.user_id, defect_id=defect_id)
        if data is None:
            raise HTTPException(status_code=404, detail="defecto no encontrado")
        cached = data["family"].get("root_cause")
        if cached and not regenerate:
            return RootCauseResponse(defect_id=defect_id, root_cause=cached, cached=True)
        # Leer la causa cacheada es lectura (viewer); calcularla y guardarla es trabajo de QA.
        enforce(access, user.user_id, Capability.QA_WORK, resource=(Resource.FAMILY, defect_id))
        r = analyzer.analyze_structured(data["family"], data["failures"])
        if r.get("confidence", 0.0) == 0.0 and not r.get("citations"):
            raise HTTPException(status_code=503, detail="el análisis IA no produjo resultado")
        # Render desde el RCA ya calculado (antes se llamaba a analyze() → 2ª llamada LLM)
        from src.assurance.root_cause import render_root_cause_markdown
        text = render_root_cause_markdown(r)[:8000]
        repo.save_root_cause(user_id=user.user_id, defect_id=defect_id, text=text)
        # Hook memoria-en-el-flujo: el RCA recién calculado deja una propuesta de
        # lección en la bandeja (si la familia la necesita). Nunca rompe la respuesta.
        if proposals is not None:
            try:
                proposals.propose_from_rca(
                    user_id=user.user_id, family=data["family"],
                    failures=data["failures"], rca=r)
            except Exception:  # noqa: BLE001 — el hook es best-effort
                logger.exception("hook causa-raíz→propuesta falló para %s", defect_id)
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
    bind_llm_org_of("test_runs", run_id)
    try:
        data = repo.get_run_assurance_data(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if data["run"] is None:
        raise HTTPException(status_code=404, detail="run not found")
    verdict = build_verdict(run_summary=data["summary"], run_families=data["families"])
    try:
        narrative = narrator.summarize(verdict)
    except Exception as exc:  # noqa: BLE001
        # La narrativa LLM es opcional: si el narrator falla (o no hay LLM), devolvemos
        # el veredicto determinista sin narrativa en lugar de romper la respuesta.
        logger.warning("narrativa del run %s no disponible: %s", run_id, type(exc).__name__)
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
    access: OrgAccess = Depends(get_org_access),
    service: ActionService = Depends(get_action_service),
) -> ProposeActionsResponse:
    enforce(access, user.user_id, Capability.QA_WORK, resource=(Resource.RUN, run_id))
    bind_llm_org_of("test_runs", run_id)
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
    access: OrgAccess = Depends(get_org_access),
    service: ActionService = Depends(get_action_service),
) -> ActionApproveResponse:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.ACTION, action_id))
    bind_llm_org_of("actions", action_id)
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
    access: OrgAccess = Depends(get_org_access),
    service: ActionService = Depends(get_action_service),
) -> ActionRejectResponse:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.ACTION, action_id))
    try:
        ok = service.reject_action(user_id=user.user_id, action_id=action_id, reason=body.reason)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return ActionRejectResponse(rejected=ok)


@router.post("/certificates/run/{run_id}", response_model=CertificateResponse)
def generate_certificate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateResponse:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.RUN, run_id))
    bind_llm_org_of("test_runs", run_id)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        return CertificateResponse(**service.generate(user_id=user.user_id, run_id=run_id,
                                                      created_at=created_at, require_admin=True))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
    return HTMLResponse(render_html(cert["canonical_json"], cert["signature"],
                                    public_url=MNEMO_PUBLIC_APP_URL))


@router.get("/certificates/{run_id}/pdf")
def get_certificate_pdf_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: CertificateService = Depends(get_certificate_service),
) -> Response:
    try:
        cert = service.get(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if cert is None:
        raise HTTPException(status_code=404, detail="certificate not found")
    try:
        pdf = render_pdf(cert["canonical_json"], cert["signature"],
                         public_url=MNEMO_PUBLIC_APP_URL)
    except Exception as exc:  # noqa: BLE001 — generación de PDF
        raise HTTPException(status_code=500, detail="No se pudo generar el PDF") from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="certificate-{run_id}.pdf"'},
    )


@router.get("/certificates/pubkey")
def certificate_pubkey_v2() -> Dict[str, str]:
    """PÚBLICO: clave pública de firma (Ed25519) para verificar certificados
    offline o vía POST /certificates/verify, sin necesidad de cuenta en Mnemo.
    Declarado antes que /certificates/{run_id} para que la ruta estática gane."""
    if not MNEMO_SIGNING_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="clave pública de firma no configurada")
    return {"algorithm": "ed25519", "public_key_pem": MNEMO_SIGNING_PUBLIC_KEY}


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
                               signature=cert["signature"], created_at=cert["created_at"],
                               share=cert.get("share", ""))


@router.post("/certificates/verify", response_model=CertificateVerifyResponse)
def verify_certificate_v2(
    body: CertificateVerifyRequest,
    service: CertificateService = Depends(get_certificate_service),
) -> CertificateVerifyResponse:
    # PÚBLICO (sin auth): la verificación es criptografía pura (firma + payload +
    # clave pública, nada secreto ni datos de ningún tenant). Un certificado que
    # solo puede verificar quien está dentro no es verificable por el auditor/
    # regulador/cliente que le da valor — es el núcleo del diferenciador.
    valido = service.verify_payload(cert=body.canonical_json, signature=body.signature)
    return CertificateVerifyResponse(valido=valido)


# ---------------------------------------------------------------------------
# Continuidad: ¿cuánto de este proyecto sabe Mnemo? + acta de traspaso firmada
# ---------------------------------------------------------------------------

@router.get("/continuity", response_model=Dict[str, Any])
def get_continuity_v2(
    org_id: str,
    project: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Sin `project`: la lista de proyectos. Con él: el índice y su desglose."""
    try:
        if project is None:
            return {"projects": list_projects(user_id=user.user_id, org_id=org_id)}
        if project not in list_projects(user_id=user.user_id, org_id=org_id):
            raise HTTPException(status_code=404, detail="proyecto no encontrado")
        idx = compute_index(user_id=user.user_id, org_id=org_id, project=project)
        if idx is None:
            # No es miembro: el MISMO 404 que un proyecto ajeno, para no filtrar
            # qué organizaciones existen.
            raise HTTPException(status_code=404, detail="proyecto no encontrado")
        return idx
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/continuity/handover", response_model=Dict[str, Any])
def emit_handover_v2(
    req: HandoverEmitRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    service: ContinuityService = Depends(get_continuity_service),
) -> Dict[str, Any]:
    """Emite el acta de traspaso del proyecto (owner/admin). created_at lo pone
    el endpoint: la lógica firmada nunca llama a now()."""
    enforce(access, user.user_id, Capability.ADMIN, org_id=req.org_id)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        return service.emit_handover(user_id=user.user_id, org_id=req.org_id,
                                     project=req.project, created_at=created_at,
                                     de=(req.de or "").strip() or None,
                                     para=(req.para or "").strip() or None)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SigningKeyMissing as exc:
        raise HTTPException(
            status_code=503,
            detail="clave de firma no configurada (MNEMO_SIGNING_PRIVATE_KEY)") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.get("/continuity/handover/latest", response_model=Dict[str, Any])
def latest_handover_v2(
    org_id: str,
    project: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ContinuityService = Depends(get_continuity_service),
) -> Dict[str, Any]:
    try:
        act = service.latest_handover(user_id=user.user_id, org_id=org_id, project=project)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if act is None:
        raise HTTPException(status_code=404, detail="sin actas de traspaso para este proyecto")
    return act


@router.post("/gate/run/{run_id}", response_model=GateResponse)
def publish_gate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    service: GateService = Depends(get_gate_service),
) -> GateResponse:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.RUN, run_id))
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


@router.post("/defects/ask", response_model=AskResponse)
def defects_ask_v2(
    req: AskRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    embedder: "LocalEmbedder" = Depends(get_embedder),
) -> AskResponse:
    enforce(access, user.user_id, Capability.READ, org_id=req.org_id)
    from src.ai.nl_query import answer_question
    bind_llm_org(req.org_id)
    try:
        emb = embedder.embed(req.question)
        families = repo.search_families_semantic(user_id=user.user_id, org_id=req.org_id,
                                                 query_embedding=emb, k=8, project=req.project)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    try:
        provider = get_llm_provider()
    except Exception:  # noqa: BLE001 — sin LLM → answer_question degrada
        provider = None
    result = answer_question(question=req.question, families=families, provider=provider)
    return AskResponse(answer=result["answer"], citations=result["citations"], families=families)


@router.get("/runs/{run_id}/briefing", response_model=BriefingResponse)
def run_briefing_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    cert_repo: CertificateRepository = Depends(get_certificate_repo),
    actions_repo: ActionRepository = Depends(get_action_repo),
) -> BriefingResponse:
    from src.ai.briefing import build_run_data, generate_briefing
    bind_llm_org_of("test_runs", run_id)
    try:
        data = repo.get_run_assurance_data(user_id=user.user_id, run_id=run_id)
        if data["run"] is None:
            raise HTTPException(status_code=404, detail="run not found")
        cert = cert_repo.get_certificate(user_id=user.user_id, run_id=run_id)
        actions = actions_repo.list_actions_for_run(user_id=user.user_id, run_id=run_id)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    run_data = build_run_data(assurance=data, certificate=cert, actions=actions)
    try:
        provider = get_llm_provider()
    except Exception:  # noqa: BLE001 — sin LLM → generate_briefing degrada
        provider = None
    b = generate_briefing(run_data=run_data, provider=provider)
    return BriefingResponse(
        verdict=(cert or {}).get("verdict") or "sin certificar",
        summary=b["summary"],
        recommendation=b["recommendation"],
        highlights=b["highlights"],
        citations=b["citations"],
    )


# ---------------------------------------------------------------------------
# /v2/graph endpoints
# ---------------------------------------------------------------------------

@router.get("/graph", response_model=Dict[str, Any])
def get_graph(
    org_id: str,
    focus: Optional[str] = None,
    limit: int = 200,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    return GraphService().build_graph(
        user_id=user.user_id,
        org_id=org_id,
        focus=focus,
        limit=min(limit, 500),
    )


@router.get("/graph/gaps", response_model=List[Dict[str, Any]])
def get_graph_gaps(
    org_id: str,
    recommendations: bool = True,
    user: AuthenticatedUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    # recommendations=false → sin LLM (solo conteo/lista): el Dashboard lo usa para
    # no bloquear ~20 s en generar recomendaciones que no muestra.
    bind_llm_org(org_id)
    return detect_gaps(user_id=user.user_id, org_id=org_id, with_recommendations=recommendations)


# ---------------------------------------------------------------------------
# /v2/knowledge endpoints
# ---------------------------------------------------------------------------

@router.post("/knowledge", response_model=Dict[str, Any])
def create_knowledge(
    req: KnowledgeCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: QaKnowledgeRepository = Depends(get_knowledge_repo),
) -> Dict[str, Any]:
    enforce(access, user.user_id, Capability.QA_WORK, org_id=req.org_id)
    try:
        item = repo.create_item(
            user_id=user.user_id, org_id=req.org_id, kind=req.kind, title=req.title,
            challenge=req.challenge, approach=req.approach, outcome=req.outcome,
            domain=req.domain, tags=req.tags, project=req.project,
            defect_family_id=req.defect_family_id, run_id=req.run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if item is None:
        raise HTTPException(status_code=403, detail="No es miembro de la organización")
    return item


@router.get("/knowledge", response_model=List[Dict[str, Any]])
def list_knowledge(
    org_id: str,
    kind: Optional[str] = None,
    domain: Optional[str] = None,
    project: Optional[str] = None,
    status: Optional[str] = None,
    defect_family_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: QaKnowledgeRepository = Depends(get_knowledge_repo),
) -> List[Dict[str, Any]]:
    try:
        return repo.list_items(user_id=user.user_id, org_id=org_id, kind=kind, domain=domain,
                               project=project, status=status,
                               defect_family_id=defect_family_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


# --- Propuestas de conocimiento (IA propone / humano aprueba) ---
# Rutas estáticas declaradas ANTES de /knowledge/{item_id} para que ganen el match.

@router.get("/knowledge/proposals", response_model=List[Dict[str, Any]])
def list_knowledge_proposals(
    org_id: str,
    status: str = "pending",
    user: AuthenticatedUser = Depends(get_current_user),
    svc: KnowledgeProposalService = Depends(get_knowledge_proposal_service),
) -> List[Dict[str, Any]]:
    try:
        return svc.list(user_id=user.user_id, org_id=org_id, status=status)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/knowledge/proposals/generate", response_model=Dict[str, int])
def generate_knowledge_proposals(
    req: KnowledgeProposalGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    svc: KnowledgeProposalService = Depends(get_knowledge_proposal_service),
) -> Dict[str, int]:
    enforce(access, user.user_id, Capability.QA_WORK, org_id=req.org_id)
    bind_llm_org(req.org_id)
    try:
        return svc.generate(user_id=user.user_id, org_id=req.org_id,
                            family_ids=req.family_ids, cap=req.cap)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/knowledge/proposals/{proposal_id}/approve", response_model=Dict[str, Any])
def approve_knowledge_proposal(
    proposal_id: str,
    req: KnowledgeProposalApproveRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    svc: KnowledgeProposalService = Depends(get_knowledge_proposal_service),
) -> Dict[str, Any]:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.PROPOSAL, proposal_id))
    try:
        item = svc.approve(
            user_id=user.user_id, proposal_id=proposal_id, kind=req.kind, title=req.title,
            challenge=req.challenge, approach=req.approach, domain=req.domain,
            outcome=req.outcome, tags=req.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if item is None:
        raise HTTPException(status_code=403,
                            detail="No autorizado (owner/admin) o la propuesta ya no está pendiente")
    return item


@router.post("/knowledge/proposals/{proposal_id}/reject", response_model=Dict[str, bool])
def reject_knowledge_proposal(
    proposal_id: str,
    req: KnowledgeProposalRejectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    svc: KnowledgeProposalService = Depends(get_knowledge_proposal_service),
) -> Dict[str, bool]:
    enforce(access, user.user_id, Capability.ADMIN, resource=(Resource.PROPOSAL, proposal_id))
    try:
        ok = svc.reject(user_id=user.user_id, proposal_id=proposal_id, reason=req.reason)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if not ok:
        raise HTTPException(status_code=403,
                            detail="No autorizado (owner/admin) o la propuesta ya no está pendiente")
    return {"rejected": True}


@router.post("/knowledge/proposals/{proposal_id}/refine", response_model=Dict[str, Any])
def refine_knowledge_proposal(
    proposal_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    svc: KnowledgeProposalService = Depends(get_knowledge_proposal_service),
) -> Dict[str, Any]:
    """UNA llamada LLM que condensa la propuesta (y propone kind/domain). Si el LLM
    cae, la propuesta queda EXACTAMENTE como estaba (nunca se pierde el determinista)."""
    enforce(access, user.user_id, Capability.QA_WORK, resource=(Resource.PROPOSAL, proposal_id))
    bind_llm_org_of("knowledge_proposals", proposal_id)
    try:
        prop = svc.repo.get_proposal(user_id=user.user_id, proposal_id=proposal_id)
        if prop is None or prop.get("status") != "pending":
            raise HTTPException(status_code=404,
                                detail="Propuesta no encontrada o ya resuelta")
        out = svc.refine(user_id=user.user_id, proposal_id=proposal_id)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if out is None:
        raise HTTPException(
            status_code=503,
            detail="El modelo de IA no está disponible ahora mismo — la propuesta queda como estaba")
    return out


# Ruta estática ANTES de /knowledge/{item_id} para que gane el match.
@router.post("/knowledge/import", response_model=KnowledgeImportResponse)
def import_knowledge(
    req: KnowledgeImportRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    svc: KnowledgeImportService = Depends(get_knowledge_import_service),
) -> KnowledgeImportResponse:
    """Import determinista desde Jira (claves) a la bandeja de propuestas. Sin LLM
    aquí: el refinado es por-propuesta. Errores por-ref en la respuesta."""
    enforce(access, user.user_id, Capability.QA_WORK, org_id=req.org_id)
    try:
        out = svc.import_refs(user_id=user.user_id, org_id=req.org_id, refs=req.refs,
                              project=req.project)
    except ImportNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ImportRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status_code=502, detail=f"Jira: {exc}") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return KnowledgeImportResponse(**out)


@router.get("/knowledge/{item_id}", response_model=Dict[str, Any])
def get_knowledge(
    item_id: str,
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: QaKnowledgeRepository = Depends(get_knowledge_repo),
) -> Dict[str, Any]:
    try:
        item = repo.get_item(user_id=user.user_id, org_id=org_id, item_id=item_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if item is None:
        raise HTTPException(status_code=404, detail="knowledge item not found")
    return item


@router.patch("/knowledge/{item_id}", response_model=Dict[str, Any])
def update_knowledge(
    item_id: str,
    req: KnowledgeUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: QaKnowledgeRepository = Depends(get_knowledge_repo),
) -> Dict[str, Any]:
    """Edita un item (incluye marcar 'obsoleto'/reactivar). Autoridad: el autor
    sobre lo suyo, owner/admin sobre cualquier item de la org."""
    enforce(access, user.user_id, Capability.QA_WORK, org_id=req.org_id)
    try:
        item = repo.update_item(user_id=user.user_id, org_id=req.org_id, item_id=item_id,
                                fields=req.model_dump(exclude={"org_id"}, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if item is None:
        raise HTTPException(status_code=404,
                            detail="item no encontrado o sin permiso (autor u owner/admin)")
    return item


@router.delete("/knowledge/{item_id}", response_model=Dict[str, bool])
def delete_knowledge(
    item_id: str,
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    repo: QaKnowledgeRepository = Depends(get_knowledge_repo),
) -> Dict[str, bool]:
    """Borrado duro (para errores). Misma autoridad que la edición."""
    enforce(access, user.user_id, Capability.QA_WORK, org_id=org_id)
    try:
        ok = repo.delete_item(user_id=user.user_id, org_id=org_id, item_id=item_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if not ok:
        raise HTTPException(status_code=404,
                            detail="item no encontrado o sin permiso (autor u owner/admin)")
    return {"deleted": True}


@router.post("/knowledge/search", response_model=List[Dict[str, Any]])
def search_knowledge(
    req: KnowledgeSearchRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    krepo: QaKnowledgeRepository = Depends(get_knowledge_repo),
    arepo: AssuranceRepository = Depends(get_assurance_repo),
    embedder=Depends(get_embedder),
) -> List[Dict[str, Any]]:
    svc = KnowledgeService(krepo, arepo, embedder=embedder)
    try:
        return svc.search_unified(user_id=user.user_id, org_id=req.org_id, query=req.query, k=req.k,
                                  project=req.project)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/knowledge/ask", response_model=Dict[str, Any])
def ask_knowledge(
    req: KnowledgeAskRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    krepo: QaKnowledgeRepository = Depends(get_knowledge_repo),
    arepo: AssuranceRepository = Depends(get_assurance_repo),
    embedder=Depends(get_embedder),
) -> Dict[str, Any]:
    enforce(access, user.user_id, Capability.READ, org_id=req.org_id)
    svc = KnowledgeService(krepo, arepo, embedder=embedder)
    bind_llm_org(req.org_id)
    try:
        return svc.ask(user_id=user.user_id, org_id=req.org_id, question=req.question,
                       project=req.project)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


# ---------------------------------------------------------------------------
# /v2/onboarding endpoints
# ---------------------------------------------------------------------------

@router.post("/onboarding/domain-summary", response_model=Dict[str, Any])
def onboarding_domain_summary(
    req: OnboardingRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    krepo: QaKnowledgeRepository = Depends(get_knowledge_repo),
    arepo: AssuranceRepository = Depends(get_assurance_repo),
    embedder=Depends(get_embedder),
) -> Dict[str, Any]:
    svc = KnowledgeService(krepo, arepo, embedder=embedder)
    bind_llm_org(req.org_id)
    return summarize_domain(knowledge_service=svc, user_id=user.user_id, org_id=req.org_id,
                            topic=req.topic, project=req.project)


@router.post("/onboarding/learning-path", response_model=Dict[str, Any])
def onboarding_learning_path(
    req: OnboardingRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    krepo: QaKnowledgeRepository = Depends(get_knowledge_repo),
    arepo: AssuranceRepository = Depends(get_assurance_repo),
    embedder=Depends(get_embedder),
) -> Dict[str, Any]:
    svc = KnowledgeService(krepo, arepo, embedder=embedder)
    bind_llm_org(req.org_id)
    return learning_path(knowledge_service=svc, user_id=user.user_id, org_id=req.org_id,
                         topic=req.topic, project=req.project)


# ---------------------------------------------------------------------------
# /v2/test-plan endpoints
# ---------------------------------------------------------------------------

@router.post("/test-plan/generate")
async def generate_test_plan_v2(
    org_id: str = Form(...),
    case_format: str = Form("manual"),
    hu_text: Optional[str] = Form(None),
    jira_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
    krepo: QaKnowledgeRepository = Depends(get_knowledge_repo),
    arepo: AssuranceRepository = Depends(get_assurance_repo),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
    embedder=Depends(get_embedder),
) -> Dict[str, Any]:
    """Generate a test plan from a user story (HU).

    HU source priority: direct text > Jira URL > uploaded file.
    """
    # Solo la lectura de la subida es IO asíncrona; Jira, el embedding, la BD y el LLM
    # (hasta 50 s) son síncronos y van al threadpool para no congelar el event loop a
    # todos los clientes (auditoría 2026-11-23 #2).
    await run_in_threadpool(enforce, access, user.user_id, Capability.QA_WORK, org_id=org_id)
    bind_llm_org(org_id)
    try:
        data = await _read_upload_capped_async(file) if (
            hu_text is None and jira_url is None and file is not None) else None

        def _work() -> Dict[str, Any]:
            if hu_text is not None:
                resolved_hu = hu_text
            elif jira_url is not None:
                resolved_hu = hu_text_from_jira(
                    url=jira_url, org_id=org_id, user_id=user.user_id, repo=integrations
                )
            elif file is not None:
                resolved_hu = resolve_hu_from_upload(file.filename, data)
            else:
                raise ValueError(
                    "No se proporcionó HU: adjunta un fichero, una URL de Jira o texto directo"
                )

            if not resolved_hu or not resolved_hu.strip():
                raise ValueError("La HU está vacía")

            ks = KnowledgeService(krepo, arepo, embedder=embedder)
            return generate_test_plan(
                knowledge_service=ks,
                user_id=user.user_id,
                org_id=org_id,
                hu_text=resolved_hu,
                case_format=case_format,
            )

        result = await run_in_threadpool(_work)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"plan": result, "citations": result.get("citations", [])}


@router.post("/test-plan/export/xray")
def export_xray_v2(
    body: TestPlanXrayExportRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
) -> Dict[str, Any]:
    """Export a test plan to Jira/Xray.

    Membership is enforced first via XrayConfig.get() before the client
    is instantiated.  Passing the returned creds as _creds= bypasses the
    internal get_raw() call that skips membership checks.
    """
    enforce(access, user.user_id, Capability.QA_WORK, org_id=body.org_id)
    try:
        config = XrayConfig()
        creds = config.get(user_id=user.user_id, org_id=body.org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if creds is None:
        raise HTTPException(
            status_code=503,
            detail="Xray no configurado para esta organización",
        )

    try:
        client = XrayClient(org_id=body.org_id, _creds=creds)
        keys = client.import_plan(plan=body.plan, case_format=body.case_format,
                                   project_key=body.project_key)
    except XrayNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except XrayImportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"keys": keys}


# ---------------------------------------------------------------------------
# /v2/automation endpoints
# ---------------------------------------------------------------------------

@router.post("/automation/generate", response_model=Dict[str, Any])
def automation_generate(
    req: AutomationGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
) -> Dict[str, Any]:
    """Genera un test Playwright (.spec.ts) a partir de un caso.

    El estilo sigue una cascada: style_sample manual → tests reales del repo
    (test_assets, few-shot) → convenciones estándar. El retrieval del few-shot
    es membership-gated (search_semantic); un no-miembro no obtiene ejemplos.
    """
    enforce(access, user.user_id, Capability.QA_WORK, org_id=req.org_id)
    if not req.case:
        raise HTTPException(status_code=400, detail="case requerido")
    bind_llm_org(req.org_id)
    examples = req.style_sample
    if not examples:
        try:
            repo = TestAssetRepository()
            examples = retrieve_style_examples(
                user_id=user.user_id, org_id=req.org_id,
                case_text=_case_text(req.case),
                asset_repo=repo, embedder=repo.embedder)
        except Exception as exc:
            logger.warning("automation few-shot retrieval failed (org=%s): %s", req.org_id, exc)
            examples = None
    return generate_playwright_test(case=req.case, style_sample=examples)


@router.post("/automation/pr", response_model=Dict[str, Any])
def automation_pr(
    req: AutomationPrRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
) -> Dict[str, Any]:
    """Open a draft PR that adds req.filename under tests/ in the org's repo.

    Sube código a una rama del repo del cliente y dispara su CI: solo owner/admin.

    Error mapping:
    - rol distinto de owner/admin    → 403
    - ValueError (GitHub not configured) → 503
    - GitHubError (API failure) → 502
    - falsy pr_url → 502
    """
    enforce(access, user.user_id, Capability.ADMIN, org_id=req.org_id)
    try:
        host = _github_codehost_factory(req.org_id, user.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="No es miembro de la organización") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    title = req.title or f"test(automation): {req.filename}"
    try:
        url = host.open_pr_with_new_file(
            title=title,
            body="Generado por Mnemo · revisa y ejecuta antes de fusionar.",
            file_path=f"tests/{req.filename}",
            content=req.code,
            marker=f"automation:{req.filename}",
        )
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not url:
        raise HTTPException(status_code=502, detail="No se pudo abrir el PR")
    return {"pr_url": url}


@router.post("/repo/index", response_model=Dict[str, Any])
def repo_index(
    req: RepoIndexRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    access: OrgAccess = Depends(get_org_access),
) -> Dict[str, Any]:
    """Index test assets from the org's GitHub repo.

    Error mapping:
    - PermissionError (non-member)         → 403
    - ValueError (GitHub not configured)   → 503
    - GitHubError (API failure)            → 502
    - GitHub not configured / no repo      → 503
    """
    enforce(access, user.user_id, Capability.QA_WORK, org_id=req.org_id)
    try:
        cfg = get_integrations_repo().get_github_config(user_id=user.user_id, org_id=req.org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="No es miembro de la organización") from exc
    if not cfg.get("configured") or not cfg.get("repo_full_name"):
        raise HTTPException(status_code=503, detail="GitHub no configurado para el org")
    try:
        host = _github_codehost_factory(req.org_id, user.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="No es miembro de la organización") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return index_repo_tests(
            user_id=user.user_id,
            org_id=req.org_id,
            repo=cfg["repo_full_name"],
            codehost=host,
            asset_repo=TestAssetRepository(),
        )
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/repo/tests", response_model=List[Dict[str, Any]])
def repo_tests(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List indexed test assets for the given org."""
    return TestAssetRepository().list_assets(user_id=user.user_id, org_id=org_id)


# Interruptor de LLM externo por organización (módulo propio: src/orgs/llm_settings_api.py).
from src.orgs.llm_settings_api import router as _llm_settings_router  # noqa: E402

router.include_router(_llm_settings_router)
