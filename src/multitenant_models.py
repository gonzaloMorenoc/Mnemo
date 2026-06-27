import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class JoinOrgRequest(BaseModel):
    join_code: str = Field(min_length=4, max_length=32)


class OrganizationResponse(BaseModel):
    id: str
    name: str
    join_code: str
    role: Optional[str] = None
    created_at: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str
    extra: Optional[Dict[str, Any]] = None


class IngestReportResponse(BaseModel):
    run_id: str
    ingested: int
    known: int
    novel: int


class DefectFamilyResponse(BaseModel):
    id: str
    title: str
    status: str
    occurrence_count: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    projects: List[str] = Field(default_factory=list)


class FailureRef(BaseModel):
    id: str
    test_name: str
    error_type: Optional[str] = None
    project: str
    source: str
    created_at: Optional[str] = None


class DefectFamilySummary(BaseModel):
    id: str
    title: str
    status: str
    occurrence_count: int
    root_cause: Optional[str] = None


class DefectLineageResponse(BaseModel):
    family: Optional[DefectFamilySummary] = None
    failures: List[FailureRef] = Field(default_factory=list)


class FamilyVerdict(BaseModel):
    id: str
    title: str
    occurrence_count: int
    recurring: bool


class AssuranceVerdictResponse(BaseModel):
    run_id: str
    ingested: int
    known: int
    novel: int
    risk: str
    top_families: List[FamilyVerdict] = Field(default_factory=list)
    narrative: Optional[str] = None


class JiraConfigRequest(BaseModel):
    org_id: str
    base_url: str
    email: str
    token: str
    jql: str = "issuetype = Bug"


class JiraConfigResponse(BaseModel):
    configured: bool
    base_url: Optional[str] = None
    email: Optional[str] = None
    jql: Optional[str] = None


class GitHubConfigRequest(BaseModel):
    org_id: str
    installation_id: str
    repo_full_name: str

    @field_validator("repo_full_name")
    @classmethod
    def _valid_repo(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", v):
            raise ValueError("repo_full_name debe tener el formato 'owner/repo'")
        return v


class GitHubConfigResponse(BaseModel):
    configured: bool
    repo_full_name: Optional[str] = None
    installation_id: Optional[str] = None


class JiraPullRequest(BaseModel):
    org_id: str
    project: str


class JiraIngestResponse(BaseModel):
    run_id: Optional[str] = None
    ingested: int
    known: int
    novel: int
    skipped: int


class RootCauseResponse(BaseModel):
    defect_id: str
    root_cause: str
    cached: bool


class CiWebhookResponse(BaseModel):
    run_id: str
    ingested: int
    known: int
    novel: int
    results_recorded: int
    snapshots_saved: int
    deduplicated: bool = False
    triage: Optional[Dict[str, int]] = None
    verdict: Optional[str] = None
    gate: Optional[str] = None


class TriageVerdictResponse(BaseModel):
    id: str
    failure_id: str
    category: str
    confidence: float
    rule_applied: str
    requires_approval: bool
    llm_assisted: bool
    status: str
    evidence_bundle: Optional[dict] = None


class ProposeActionsResponse(BaseModel):
    quarantine: int = 0
    ticket: int = 0
    self_heal: int = 0
    skipped: int = 0


class ActionResponse(BaseModel):
    id: str
    triage_verdict_id: str
    run_id: str
    org_id: Optional[str] = None
    kind: str
    payload: Optional[dict] = None
    summary: Optional[str] = None
    status: str
    artifact_ref: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    reject_reason: Optional[str] = None


class ActionRejectRequest(BaseModel):
    reason: str = ""


class ActionApproveResponse(BaseModel):
    approved: bool
    materialized: bool = False
    artifact_ref: Optional[str] = None


class ActionRejectResponse(BaseModel):
    rejected: bool


class CertificateResponse(BaseModel):
    run_id: str
    verdict: str
    risk_score: int
    canonical_json: dict
    signature: str
    created_at: Optional[str] = None


class CertificateVerifyRequest(BaseModel):
    canonical_json: dict
    signature: str


class CertificateVerifyResponse(BaseModel):
    valido: bool


class GateResponse(BaseModel):
    verdict: str
    conclusion: str
    check_run_url: str


class SetFamilyLabelRequest(BaseModel):
    label: str
    reason: Optional[str] = None


class FamilyLabelResponse(BaseModel):
    family_id: str
    label: str


class CalibrationMetricsResponse(BaseModel):
    total: int
    aciertos: int
    accuracy: float
    familias_calibradas: int
    por_categoria: dict


class AskRequest(BaseModel):
    org_id: str
    question: str = Field(max_length=2000)


class AskResponse(BaseModel):
    answer: str
    citations: List[str]
    families: List[Dict[str, Any]]


class BriefingResponse(BaseModel):
    verdict: str
    summary: str
    recommendation: str
    highlights: List[str]
    citations: List[str]
