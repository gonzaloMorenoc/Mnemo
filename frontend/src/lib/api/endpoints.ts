import { apiRequest } from "@/lib/api/client";
import type {
  ActionApproveResult,
  ActionItem,
  ActionRejectResult,
  AnalyzeV2Request,
  AnalyzeV2Response,
  AssuranceVerdictResponse,
  Certificate,
  DefectFamilyResponse,
  DefectLineageResponse,
  GateResult,
  HealthResponse,
  IngestReportResponse,
  JiraConfigResponse,
  JiraIngestResponse,
  OrganizationResponse,
  ProposeActionsResult,
  RootCauseResponse,
  TriageVerdict,
  UploadResponse,
} from "@/lib/api/types";

export function getOrganizations(token: string) {
  return apiRequest<OrganizationResponse[]>("/api/v2/orgs", "GET", { token });
}

export function createOrganization(token: string, payload: { name: string }) {
  return apiRequest<OrganizationResponse>("/api/v2/orgs", "POST", { token, body: payload });
}

export function joinOrganization(token: string, payload: { join_code: string }) {
  return apiRequest<OrganizationResponse>("/api/v2/orgs/join", "POST", { token, body: payload });
}

export function analyzeError(token: string, payload: AnalyzeV2Request) {
  return apiRequest<AnalyzeV2Response>("/api/v2/analyze", "POST", {
    token,
    body: payload as unknown as Record<string, unknown>,
  });
}

export function uploadKnowledge(token: string, payload: FormData) {
  return apiRequest<UploadResponse>("/api/v2/upload", "POST", { token, body: payload });
}

export function getHealth() {
  return apiRequest<HealthResponse>("/api/health", "GET");
}

export function ingestReport(token: string, payload: FormData) {
  return apiRequest<IngestReportResponse>("/api/v2/ingest/report", "POST", { token, body: payload });
}

export function getDefects(token: string, orgId: string) {
  return apiRequest<DefectFamilyResponse[]>(
    `/api/v2/defects?org_id=${encodeURIComponent(orgId)}`,
    "GET",
    { token },
  );
}

export function getDefectLineage(token: string, defectId: string) {
  return apiRequest<DefectLineageResponse>(
    `/api/v2/defects/${encodeURIComponent(defectId)}`,
    "GET",
    { token },
  );
}

export function getAssuranceVerdict(token: string, runId: string) {
  return apiRequest<AssuranceVerdictResponse>(
    `/api/v2/assurance/run/${encodeURIComponent(runId)}`,
    "GET",
    { token },
  );
}

export function getJiraConfig(token: string, orgId: string) {
  return apiRequest<JiraConfigResponse>(
    `/api/v2/integrations/jira?org_id=${encodeURIComponent(orgId)}`,
    "GET",
    { token },
  );
}

export function saveJiraConfig(token: string, body: Record<string, unknown>) {
  return apiRequest<JiraConfigResponse>("/api/v2/integrations/jira", "POST", { token, body });
}

export function pullJiraBugs(token: string, body: Record<string, unknown>) {
  return apiRequest<JiraIngestResponse>("/api/v2/ingest/jira/pull", "POST", { token, body });
}

export function ingestJiraFile(token: string, form: FormData) {
  return apiRequest<JiraIngestResponse>("/api/v2/ingest/jira/file", "POST", { token, body: form });
}

export function analyzeRootCause(
  token: string,
  defectId: string,
  regenerate = false,
): Promise<RootCauseResponse> {
  return apiRequest<RootCauseResponse>(
    `/api/v2/defects/${encodeURIComponent(defectId)}/root-cause?regenerate=${regenerate}`,
    "POST",
    { token },
  );
}

export function getTriageVerdicts(token: string, runId: string) {
  return apiRequest<TriageVerdict[]>(
    `/api/v2/triage/run/${encodeURIComponent(runId)}`, "GET", { token });
}

export function proposeActions(token: string, runId: string) {
  return apiRequest<ProposeActionsResult>(
    `/api/v2/actions/run/${encodeURIComponent(runId)}/propose`, "POST", { token });
}

export function getActions(token: string, orgId: string, status?: string) {
  const qs = new URLSearchParams({ org_id: orgId });
  if (status) qs.set("status", status);
  return apiRequest<ActionItem[]>(`/api/v2/actions?${qs.toString()}`, "GET", { token });
}

export function approveAction(token: string, actionId: string) {
  return apiRequest<ActionApproveResult>(
    `/api/v2/actions/${encodeURIComponent(actionId)}/approve`, "POST", { token });
}

export function rejectAction(token: string, actionId: string, reason = "") {
  return apiRequest<ActionRejectResult>(
    `/api/v2/actions/${encodeURIComponent(actionId)}/reject`, "POST", { token, body: { reason } });
}

export function generateCertificate(token: string, runId: string) {
  return apiRequest<Certificate>(
    `/api/v2/certificates/run/${encodeURIComponent(runId)}`, "POST", { token });
}

export function getCertificate(token: string, runId: string) {
  return apiRequest<Certificate>(
    `/api/v2/certificates/${encodeURIComponent(runId)}`, "GET", { token });
}

export function publishGate(token: string, runId: string) {
  return apiRequest<GateResult>(
    `/api/v2/gate/run/${encodeURIComponent(runId)}`, "POST", { token });
}
