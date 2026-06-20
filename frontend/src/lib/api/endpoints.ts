import { apiRequest } from "@/lib/api/client";
import type {
  AnalyzeV2Request,
  AnalyzeV2Response,
  AssuranceVerdictResponse,
  DefectFamilyResponse,
  DefectLineageResponse,
  HealthResponse,
  IngestReportResponse,
  OrganizationResponse,
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
  return apiRequest<AnalyzeV2Response>("/api/v2/analyze", "POST", { token, body: payload });
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
