export type ChunkSourceType =
  | "oem_manual_section"
  | "oem_manual_table_row"
  | "oem_manual_figure_semantic"
  | "historical_insight"
  | "historical_insight_span";

export type ManualIngestJobStatus = "pending" | "running" | "succeeded" | "failed";
export type Criticality = "low" | "medium" | "high";
export type Urgency = "low" | "medium" | "high";

export interface ExcerptRef {
  start_line: number;
  end_line: number;
}

export interface SourceRef {
  doc_id?: string | null;
  page?: number | null;
  link?: string | null;
  path?: string | null;
  table_id?: string | null;
  row?: number | null;
  figure_id?: string | null;
  excerpt?: ExcerptRef | null;
}

export interface ExtractionMetadata {
  method: string;
  field_confidence: Record<string, number>;
  candidate_fields: Record<string, unknown>;
}

export interface KnowledgeChunk {
  chunk_id: string;
  tenant_id: string;
  source_type: ChunkSourceType;
  text: string;
  source_ref: SourceRef;
  site_id?: string | null;
  manufacturer?: string | null;
  machine_id?: string | null;
  machine_model?: string | null;
  machine_family?: string | null;
  manual_version?: string | null;
  page?: number | null;
  section_path: string[];
  component: string[];
  issue_type: string[];
  structured_fields: Record<string, string>;
  timestamp?: string | null;
  extraction?: ExtractionMetadata | null;
  resolution_status?: string | null;
  content_confidence: number;
  parent_chunk_id?: string | null;
}

export interface AssetMetadata {
  tenant_id: string;
  site_id: string;
  machine_id: string;
  machine_model: string;
  machine_family?: string | null;
  criticality: Criticality;
  active_manual_version?: string | null;
  aliases: string[];
}

export interface CheckRecord {
  check: string;
  status: "pending" | "completed" | "skipped";
}

export interface Hypothesis {
  cause: string;
  confidence: number;
}

export interface SessionState {
  issue_summary?: string | null;
  measurements: Record<string, unknown>;
  checks_completed: CheckRecord[];
  hypotheses: Hypothesis[];
  next_actions: string[];
}

export interface SessionRecord {
  session_id: string;
  tenant_id: string;
  user_id: string;
  machine_id: string;
  work_order_id?: string | null;
  opened_at: string;
  state: SessionState;
  last_context_summary?: string | null;
  updated_at: string;
}

export interface SupportingEvidence {
  citation_id: string;
  source_type: "oem_manual" | "historical_log";
  citation: string;
  excerpt: string;
}

export interface SuspectedCause {
  cause: string;
  why: string;
  confidence: number;
}

export interface RecommendedCheck {
  step: string;
  expected: string;
  stop_if: string;
  citations: string[];
}

export interface CopilotAnswer {
  issue_summary: string;
  suspected_causes: SuspectedCause[];
  recommended_checks: RecommendedCheck[];
  required_tools: string[];
  safety_warnings: string[];
  supporting_evidence: SupportingEvidence[];
  confidence: number;
  urgency: Urgency;
  escalate_if: string[];
  follow_up_question?: string | null;
}

export interface AnswerEnvelope {
  session_id: string;
  tenant_id: string;
  answer: CopilotAnswer;
}

export interface ManualPageSeed {
  page: number;
  text?: string;
  section_path?: string[];
  table_rows?: Record<string, string>[];
  visual_summaries?: string[];
}

export interface IngestManualRequest {
  doc_id: string;
  manufacturer: string;
  machine_model: string;
  machine_family?: string | null;
  manual_version: string;
  pdf_path?: string | null;
  pages?: ManualPageSeed[];
  activate_version?: boolean;
  tenant_id?: string | null;
}

export interface ManualIngestJobRecord {
  job_id: string;
  tenant_id: string;
  status: ManualIngestJobStatus;
  request: IngestManualRequest;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  attempts: number;
  error_message?: string | null;
  result?: Record<string, unknown> | null;
}

export interface IngestLogRequest {
  machine_id: string;
  site_id: string;
  machine_model: string;
  machine_family?: string | null;
  timestamp?: string | null;
  path: string;
  markdown: string;
  resolution_status?: string;
  tenant_id?: string | null;
}

export interface AnswerRequest {
  message: string;
  machine_id: string;
  site_id?: string | null;
  machine_model?: string | null;
  machine_family?: string | null;
  criticality?: Criticality;
  session_id?: string | null;
  work_order_id?: string | null;
  measurements?: Record<string, unknown>;
  completed_checks?: string[];
  tenant_id?: string | null;
}

export interface CreateSessionRequest {
  machine_id: string;
  site_id: string;
  machine_model: string;
  machine_family?: string | null;
  criticality?: Criticality;
  work_order_id?: string | null;
  aliases?: string[];
  tenant_id?: string | null;
}

export interface IngestResult {
  corpus: "oem_manuals" | "historical_insights";
  namespace: string;
  chunk_count: number;
  chunk_ids: string[];
}

export interface HealthResponse {
  status: "ok";
  environment: string;
}
