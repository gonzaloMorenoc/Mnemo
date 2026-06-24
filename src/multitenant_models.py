from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class JoinOrgRequest(BaseModel):
    join_code: str = Field(min_length=4, max_length=32)


class AnalyzeV2Request(BaseModel):
    error_log: str = Field(min_length=10)
    org_id: Optional[str] = None
    top_k: int = Field(default=8, ge=1, le=20)


class ScopeSource(BaseModel):
    scope: Literal["org", "user", "global"]
    source_title: str
    similarity: float


class StructuredAnalysisPayload(BaseModel):
    root_cause: str
    why_it_happened: str
    how_to_fix: str
    suggested_patch_steps: List[str]
    confidence: float


class AnalyzeV2Response(BaseModel):
    analysis: StructuredAnalysisPayload
    sources: List[ScopeSource]
    source_scopes: List[Literal["org", "user", "global"]]
    analysis_id: Optional[int] = None


class UploadResponse(BaseModel):
    document_id: str
    global_document_id: Optional[str] = None
    chunk_count: int
    storage_path: str


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
    artifact_ref: Optional[str] = None


class ActionRejectResponse(BaseModel):
    rejected: bool
