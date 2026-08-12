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
  label?: string | null;
  has_lesson?: boolean;
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
  family: {
    id: string;
    title: string;
    status: string;
    occurrence_count: number;
    /** Razón de la última etiqueta humana — el "por qué" de quien la puso. */
    label_reason?: string | null;
  } | null;
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

export interface GitHubConfigResponse {
  configured: boolean;
  repo_full_name: string | null;
  installation_id: string | null;
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

export interface IngestToken {
  id: string;
  name: string;
  created_at?: string | null;
  last_used_at?: string | null;
  revoked_at?: string | null;
}

export interface IngestTokenCreated extends IngestToken {
  token: string; // el claro SOLO viaja en la creación
}

export interface RunListItem {
  id: string;
  project: string;
  source: string;
  commit_sha?: string | null;
  created_at?: string | null;
  verdict?: string | null;
  risk_score?: number | null;
  failures: number;
}

export interface KnowledgeProposal {
  id: string;
  org_id: string;
  defect_family_id: string | null;
  run_id?: string | null;
  kind: string;
  title: string;
  challenge?: string | null;
  approach?: string | null;
  domain?: string | null;
  outcome?: string | null;
  tags: string[];
  status: string;
  created_at?: string | null;
  source: "auto_triage" | "jira" | "confluence";
  external_ref?: string | null;
  external_url?: string | null;
  project?: string | null;
}

export interface KnowledgeImportResult {
  created: KnowledgeProposal[];
  refreshed: KnowledgeProposal[];
  skipped: string[];
  /** Secciones de una página que no entraron (tope por página o cupo horario). */
  skipped_sections?: { ref: string; descartadas: number }[];
  errors: { ref: string; reason: string }[];
}

export interface GenerateProposalsResult {
  created: number;
  failed: number;
  remaining: number;
}

export interface ActionApproveResult {
  approved: boolean;
  materialized: boolean;
  artifact_ref?: string | null;
}

export interface ActionRejectResult {
  rejected: boolean;
}

export interface ExecutionManifest {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  flaky?: number;
  complete: boolean;
  source_format: string;
  artifact_sha256: string;
  commit_sha?: string | null;
}

export interface Certificate {
  run_id: string;
  verdict: string;
  risk_score: number;
  // El manifiesto va DENTRO del acta firmada → se lee de canonical_json.execution_manifest.
  canonical_json: Record<string, unknown>;
  signature: string;
  // Sobre compartible que emite el backend (base64url del acta + su firma).
  // Vacío o ausente si el acta no cabe en un enlace usable.
  share?: string;
  created_at?: string | null;
}

export interface CertificateVerifyResponse {
  valido: boolean;
}

export interface CertificatePubkey {
  algorithm: string;
  public_key_pem: string;
}

export interface GateResult {
  verdict: string;
  conclusion: string;
  check_run_url: string;
}

export interface CalibrationMetrics {
  total: number;
  aciertos: number;
  accuracy: number;
  familias_calibradas: number;
  por_categoria: Record<string, number>;
}

export interface FamilyLabel {
  family_id: string;
  label: string;
}

export interface BriefingResponse {
  verdict: string;
  summary: string;
  recommendation: string;
  highlights: string[];
  citations: string[];
}

export interface KnowledgeItem {
  id: string;
  kind: string;
  title: string;
  challenge?: string;
  approach?: string;
  outcome?: string;
  domain?: string;
  tags: string[];
  confidence: string;
  created_at: string;
  project?: string | null;
  source?: string;
  source_url?: string | null;
  status?: string;
  created_by?: string;
  updated_at?: string | null;
}

export interface KnowledgeSource {
  id: string;
  type: "knowledge" | "defect";
  title?: string;
  content: string;
  confidence?: string;
}

export interface KnowledgeAnswer {
  answer: string;
  citations: string[];
}

export type AutoGenCase = { title: string; steps: string[] };

export interface TestCase {
  title: string;
  level: string;
  priority: string;
  automatable: boolean;
  steps?: string[];
  expected?: string;
  gherkin?: string;
}

export interface TestPlan {
  summary: string;
  systems: string[];
  risks: string[];
  preconditions: string[];
  test_data: string[];
  cases: TestCase[];
  gaps: string[];
  open_questions: string[];
  citations: string[];
}

export interface TestPlanResult {
  plan: TestPlan;
  citations: string[];
}

export interface DomainSummary {
  rules: string[];
  systems: string[];
  existing_tests: string[];
  historical_bugs: string[];
  risks: string[];
  citations: string[];
}

export interface LearningDay {
  day: number;
  items: string[];
}

export interface LearningPath {
  days: LearningDay[];
  citations: string[];
}

export interface GeneratedTest {
  code: string;
  filename: string;
  notes: string;
}

export interface GraphNode {
  id: string;
  type: "knowledge" | "defect" | "domain";
  label: string;
  kind?: string;
  domain?: string;
  count?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: "documenta" | "pertenece" | "tag";
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CoverageGap {
  kind: string;
  title: string;
  severity: "alta" | "media" | "baja";
  affected: string[];
  recommendation: string;
}

export interface TestAsset {
  path: string;
  framework: string;
  domain: string;
}

export interface RepoIndexResult {
  indexed: number;
  by_domain: Record<string, number>;
  skipped: number;
}
