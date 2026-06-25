export type Scope = "org" | "user" | "global";

export interface ApiErrorShape {
  detail?: string;
  message?: string;
}

export interface OrganizationResponse {
  id: string;
  name: string;
  join_code: string;
  role: string | null;
  created_at: string | null;
}

export interface AnalyzeV2Request {
  error_log: string;
  org_id?: string;
  top_k?: number;
}

export interface AnalyzeV2Response {
  analysis: {
    root_cause: string;
    why_it_happened: string;
    how_to_fix: string;
    suggested_patch_steps: string[];
    confidence: number;
  };
  sources: Array<{
    scope: "org" | "user" | "global";
    source_title: string;
    similarity: number;
  }>;
  source_scopes: Array<"org" | "user" | "global">;
  analysis_id: number | null;
}

export interface UploadResponse {
  document_id: string;
  global_document_id: string | null;
  chunk_count: number;
  storage_path: string;
}

export interface HealthResponse {
  status: string;
  model: string;
  multi_tenant_enabled: boolean;
}

export interface IngestReportResponse {
  run_id: string;
  ingested: number;
  known: number;
  novel: number;
}

export interface DefectFamilyResponse {
  id: string;
  title: string;
  status: string;
  occurrence_count: number;
  first_seen: string | null;
  last_seen: string | null;
  projects: string[];
}

export interface FailureRef {
  id: string;
  test_name: string;
  error_type: string | null;
  project: string;
  source: string;
  created_at: string | null;
}

export interface DefectLineageResponse {
  family: { id: string; title: string; status: string; occurrence_count: number } | null;
  failures: FailureRef[];
}

export interface FamilyVerdict {
  id: string;
  title: string;
  occurrence_count: number;
  recurring: boolean;
}

export interface AssuranceVerdictResponse {
  run_id: string;
  ingested: number;
  known: number;
  novel: number;
  risk: "ok" | "atencion";
  top_families: FamilyVerdict[];
  narrative: string | null;
}

export interface JiraConfigResponse {
  configured: boolean;
  base_url: string | null;
  email: string | null;
  jql: string | null;
}

export interface JiraIngestResponse {
  run_id: string | null;
  ingested: number;
  known: number;
  novel: number;
  skipped: number;
}

export interface RootCauseResponse {
  defect_id: string;
  root_cause: string;
  cached: boolean;
}

export interface TriageVerdict {
  id: string;
  failure_id: string;
  category: string;
  confidence: number;
  rule_applied: string;
  requires_approval: boolean;
  llm_assisted: boolean;
  status: string;
  evidence_bundle?: Record<string, unknown> | null;
}

export interface ActionItem {
  id: string;
  triage_verdict_id: string;
  run_id: string;
  org_id?: string | null;
  kind: string;
  payload?: Record<string, unknown> | null;
  summary?: string | null;
  status: string;
  artifact_ref?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  reject_reason?: string | null;
}

export interface ProposeActionsResult {
  quarantine: number;
  ticket: number;
  self_heal: number;
  skipped: number;
}

export interface ActionApproveResult {
  approved: boolean;
  materialized: boolean;
  artifact_ref?: string | null;
}

export interface ActionRejectResult {
  rejected: boolean;
}

export interface Certificate {
  run_id: string;
  verdict: string;
  risk_score: number;
  canonical_json: Record<string, unknown>;
  signature: string;
  created_at?: string | null;
}

export interface GateResult {
  verdict: string;
  conclusion: string;
  check_run_url: string;
}
