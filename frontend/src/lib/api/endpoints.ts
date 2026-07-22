import { apiRequest } from "@/lib/api/client";
import type {
  ActionApproveResult,
  ActionItem,
  ActionRejectResult,
  AssuranceVerdictResponse,
  AutoGenCase,
  BriefingResponse,
  CalibrationMetrics,
  Certificate,
  CertificatePubkey,
  CertificateVerifyResponse,
  CoverageGap,
  DefectFamilyResponse,
  DefectLineageResponse,
  DomainSummary,
  FamilyLabel,
  GateResult,
  GeneratedTest,
  GitHubConfigResponse,
  Graph,
  HealthResponse,
  IngestReportResponse,
  JiraConfigResponse,
  JiraIngestResponse,
  GenerateProposalsResult,
  KnowledgeAnswer,
  KnowledgeItem,
  KnowledgeProposal,
  KnowledgeSource,
  LearningPath,
  OrganizationResponse,
  ProposeActionsResult,
  RepoIndexResult,
  RootCauseResponse,
  TestAsset,
  TestCase,
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

// Verificación PÚBLICA — sin token: cualquiera (auditor, cliente, regulador)
// valida la firma de un acta sin cuenta en Mnemo.
//
// Recibe el TEXTO CRUDO del acta (tal como se pegó) y lo reenvía verbatim: NO
// se hace JSON.parse + JSON.stringify, porque JS reformatea los números al
// re-serializar (p. ej. el float `0.0` de Python se colapsa a `0`) y eso
// cambiaría un byte del payload → la firma daría inválida. El proxy de Next y
// el backend leen el texto tal cual, así que la canonicalización coincide.
export function verifyCertificate(rawActa: string) {
  return apiRequest<CertificateVerifyResponse>(
    "/api/v2/certificates/verify",
    "POST",
    { body: rawActa, headers: { "Content-Type": "application/json" } },
  );
}

export function getCertificatePubkey() {
  return apiRequest<CertificatePubkey>("/api/v2/certificates/pubkey", "GET", {});
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

// --- Propuestas de conocimiento (IA propone / humano aprueba) ---

export function listKnowledgeProposals(token: string, orgId: string, status = "pending") {
  const qs = new URLSearchParams({ org_id: orgId, status });
  return apiRequest<KnowledgeProposal[]>(
    `/api/v2/knowledge/proposals?${qs.toString()}`, "GET", { token });
}

export function generateKnowledgeProposals(token: string, orgId: string, cap = 5) {
  return apiRequest<GenerateProposalsResult>(
    "/api/v2/knowledge/proposals/generate", "POST", { token, body: { org_id: orgId, cap } });
}

export function approveKnowledgeProposal(
  token: string, proposalId: string, body: Record<string, unknown>,
) {
  return apiRequest<KnowledgeItem>(
    `/api/v2/knowledge/proposals/${encodeURIComponent(proposalId)}/approve`, "POST", { token, body });
}

export function rejectKnowledgeProposal(token: string, proposalId: string, reason = "") {
  return apiRequest<{ rejected: boolean }>(
    `/api/v2/knowledge/proposals/${encodeURIComponent(proposalId)}/reject`, "POST",
    { token, body: { reason } });
}

export function generateTestPlan(token: string, form: FormData) {
  return apiRequest<TestPlanResult>("/api/v2/test-plan/generate", "POST", { token, body: form });
}

export function domainSummary(token: string, body: { org_id: string; topic: string }) {
  return apiRequest<DomainSummary>("/api/v2/onboarding/domain-summary", "POST", { token, body });
}

export function learningPath(token: string, body: { org_id: string; topic: string }) {
  return apiRequest<LearningPath>("/api/v2/onboarding/learning-path", "POST", { token, body });
}

export function exportTestPlanXray(
  token: string,
  body: { org_id: string; plan: TestPlan; case_format: string },
) {
  return apiRequest<{ keys: string[] }>("/api/v2/test-plan/export/xray", "POST", { token, body });
}

export function generatePlaywrightTest(
  token: string,
  body: { case: TestCase | AutoGenCase; org_id: string; style_sample?: string },
) {
  return apiRequest<GeneratedTest>("/api/v2/automation/generate", "POST", { token, body });
}

export function getKnowledgeItem(token: string, params: { org_id: string; id: string }) {
  return apiRequest<KnowledgeItem>(
    `/api/v2/knowledge/${encodeURIComponent(params.id)}?org_id=${encodeURIComponent(params.org_id)}`,
    "GET",
    { token },
  );
}

export function openAutomationPr(
  token: string,
  body: { org_id: string; code: string; filename: string; title?: string },
) {
  return apiRequest<{ pr_url: string }>("/api/v2/automation/pr", "POST", { token, body });
}

export function getGraph(
  token: string,
  params: { org_id: string; focus?: string; limit?: number },
) {
  const q = new URLSearchParams({ org_id: params.org_id });
  if (params.focus) q.set("focus", params.focus);
  if (params.limit) q.set("limit", String(params.limit));
  return apiRequest<Graph>(`/api/v2/graph?${q.toString()}`, "GET", { token });
}

export function getGaps(
  token: string,
  params: { org_id: string; recommendations?: boolean },
) {
  let path = `/api/v2/graph/gaps?org_id=${encodeURIComponent(params.org_id)}`;
  // recommendations=false → el backend no llama al LLM (solo conteo/lista): el Dashboard
  // lo usa para no esperar ~20 s a recomendaciones que no muestra.
  if (params.recommendations === false) path += "&recommendations=false";
  return apiRequest<CoverageGap[]>(
    path,
    "GET",
    { token },
  );
}

export function getGithubConfig(token: string, params: { org_id: string }) {
  return apiRequest<GitHubConfigResponse>(
    `/api/v2/integrations/github?org_id=${encodeURIComponent(params.org_id)}`,
    "GET",
    { token },
  );
}

export function saveGithubConfig(
  token: string,
  body: { org_id: string; installation_id: string; repo_full_name: string },
) {
  return apiRequest<GitHubConfigResponse>("/api/v2/integrations/github", "POST", { token, body });
}

export function indexRepo(token: string, body: { org_id: string }) {
  return apiRequest<RepoIndexResult>("/api/v2/repo/index", "POST", { token, body });
}

export function listRepoTests(token: string, params: { org_id: string }) {
  return apiRequest<TestAsset[]>(
    `/api/v2/repo/tests?org_id=${encodeURIComponent(params.org_id)}`,
    "GET",
    { token },
  );
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
