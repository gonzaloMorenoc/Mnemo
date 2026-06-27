import { apiRequest } from "@/lib/api/client";
import type {
  ActionApproveResult,
  ActionItem,
  ActionRejectResult,
  AssuranceVerdictResponse,
  BriefingResponse,
  CalibrationMetrics,
  Certificate,
  DefectFamilyResponse,
  DefectLineageResponse,
  FamilyLabel,
  GateResult,
  HealthResponse,
  IngestReportResponse,
  JiraConfigResponse,
  JiraIngestResponse,
  KnowledgeAnswer,
  KnowledgeItem,
  KnowledgeSource,
  OrganizationResponse,
  ProposeActionsResult,
  RootCauseResponse,
  TestPlan,
  TestPlanResult,
  TriageVerdict,
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

export function getCalibrationMetrics(token: string, orgId: string) {
  return apiRequest<CalibrationMetrics>(
    `/api/v2/calibration/metrics?org_id=${encodeURIComponent(orgId)}`, "GET", { token });
}

export function setFamilyLabel(token: string, familyId: string, label: string, reason = "") {
  return apiRequest<FamilyLabel>(
    `/api/v2/defects/${encodeURIComponent(familyId)}/label`, "PATCH", { token, body: { label, reason } });
}

export function getBriefing(token: string, runId: string) {
  return apiRequest<BriefingResponse>(
    `/api/v2/runs/${encodeURIComponent(runId)}/briefing`,
    "GET",
    { token },
  );
}

export function createKnowledge(token: string, body: Record<string, unknown>) {
  return apiRequest<KnowledgeItem>("/api/v2/knowledge", "POST", { token, body });
}

export function listKnowledge(token: string, orgId: string, kind?: string) {
  const qs = new URLSearchParams({ org_id: orgId });
  if (kind) qs.set("kind", kind);
  return apiRequest<KnowledgeItem[]>(`/api/v2/knowledge?${qs.toString()}`, "GET", { token });
}

export function searchKnowledge(
  token: string,
  body: { org_id: string; query: string; k?: number },
) {
  return apiRequest<KnowledgeSource[]>("/api/v2/knowledge/search", "POST", { token, body });
}

export function askKnowledge(token: string, body: { org_id: string; question: string }) {
  return apiRequest<KnowledgeAnswer>("/api/v2/knowledge/ask", "POST", { token, body });
}

export function generateTestPlan(token: string, form: FormData) {
  return apiRequest<TestPlanResult>("/api/v2/test-plan/generate", "POST", { token, body: form });
}

export function exportTestPlanXray(
  token: string,
  body: { org_id: string; plan: TestPlan; case_format: string },
) {
  return apiRequest<{ keys: string[] }>("/api/v2/test-plan/export/xray", "POST", { token, body });
}

export async function getCertificatePdf(token: string, runId: string): Promise<Blob> {
  const res = await fetch(`/api/v2/certificates/${encodeURIComponent(runId)}/pdf`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Descarga fallida (${res.status})`);
  return res.blob();
}
