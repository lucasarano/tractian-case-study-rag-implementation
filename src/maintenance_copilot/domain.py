from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ChunkSourceType(StrEnum):
    OEM_MANUAL_SECTION = "oem_manual_section"
    OEM_MANUAL_TABLE_ROW = "oem_manual_table_row"
    OEM_MANUAL_FIGURE_SEMANTIC = "oem_manual_figure_semantic"
    HISTORICAL_INSIGHT = "historical_insight"
    HISTORICAL_INSIGHT_SPAN = "historical_insight_span"


class ManualIngestJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExcerptRef(BaseModel):
    start_line: int
    end_line: int


class SourceRef(BaseModel):
    doc_id: str | None = None
    page: int | None = None
    link: str | None = None
    path: str | None = None
    table_id: str | None = None
    row: int | None = None
    figure_id: str | None = None
    excerpt: ExcerptRef | None = None

    def render(self) -> str:
        if self.link:
            return self.link
        if self.path and self.excerpt:
            return f"{self.path} lines {self.excerpt.start_line}-{self.excerpt.end_line}"
        if self.doc_id and self.page:
            return f"{self.doc_id}#page={self.page}"
        if self.path:
            return self.path
        return "unknown-source"


class ExtractionMetadata(BaseModel):
    method: str = "rules"
    field_confidence: dict[str, float] = Field(default_factory=dict)
    candidate_fields: dict[str, Any] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    chunk_id: str
    tenant_id: str
    source_type: ChunkSourceType
    text: str
    source_ref: SourceRef
    site_id: str | None = None
    manufacturer: str | None = None
    machine_id: str | None = None
    machine_model: str | None = None
    machine_family: str | None = None
    manual_version: str | None = None
    page: int | None = None
    section_path: list[str] = Field(default_factory=list)
    component: list[str] = Field(default_factory=list)
    issue_type: list[str] = Field(default_factory=list)
    structured_fields: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime | None = None
    extraction: ExtractionMetadata | None = None
    resolution_status: str | None = None
    content_confidence: float = 1.0
    parent_chunk_id: str | None = None

    @property
    def is_manual(self) -> bool:
        return self.source_type in {
            ChunkSourceType.OEM_MANUAL_SECTION,
            ChunkSourceType.OEM_MANUAL_TABLE_ROW,
            ChunkSourceType.OEM_MANUAL_FIGURE_SEMANTIC,
        }

    @property
    def source_family(self) -> Literal["oem_manual", "historical_log"]:
        return "oem_manual" if self.is_manual else "historical_log"

    def citation(self) -> str:
        return self.source_ref.render()

    def metadata(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "machine_id": self.machine_id,
            "machine_model": self.machine_model,
            "machine_family": self.machine_family,
            "component": self.component,
            "issue_type": self.issue_type,
            "source_type": self.source_type.value,
            "manual_version": self.manual_version,
            "page": self.page,
            "section_path": self.section_path,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "resolution_status": self.resolution_status,
            "content_confidence": self.content_confidence,
        }

    def excerpt(self, limit: int = 220) -> str:
        text = " ".join(self.text.split())
        return text if len(text) <= limit else f"{text[: limit - 3]}..."


class AssetMetadata(BaseModel):
    tenant_id: str
    site_id: str
    machine_id: str
    machine_model: str
    machine_family: str | None = None
    criticality: Literal["low", "medium", "high"] = "medium"
    active_manual_version: str | None = None
    aliases: list[str] = Field(default_factory=list)


class ManualModelBinding(BaseModel):
    tenant_id: str
    machine_model: str
    machine_family: str | None = None
    doc_id: str
    manual_version: str
    is_active: bool = True
    updated_at: datetime


class CheckRecord(BaseModel):
    check: str
    status: Literal["pending", "completed", "skipped"] = "pending"


class Hypothesis(BaseModel):
    cause: str
    confidence: float


class SessionState(BaseModel):
    issue_summary: str | None = None
    measurements: dict[str, Any] = Field(default_factory=dict)
    checks_completed: list[CheckRecord] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class SessionRecord(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    machine_id: str
    work_order_id: str | None = None
    opened_at: datetime
    state: SessionState = Field(default_factory=SessionState)
    last_context_summary: str | None = None
    updated_at: datetime


class VerifiedIdentity(BaseModel):
    subject: str
    tenant_id: str
    raw_claims: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: KnowledgeChunk
    corpus: Literal["oem_manuals", "historical_insights"]
    score: float
    rerank_score: float | None = None

    @property
    def blended_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.score


class SupportingEvidence(BaseModel):
    citation_id: str
    source_type: Literal["oem_manual", "historical_log"]
    citation: str
    excerpt: str


class SuspectedCause(BaseModel):
    cause: str
    why: str
    confidence: float


class RecommendedCheck(BaseModel):
    step: str
    expected: str
    stop_if: str
    citations: list[str] = Field(min_length=1)


class CopilotAnswer(BaseModel):
    issue_summary: str
    suspected_causes: list[SuspectedCause]
    recommended_checks: list[RecommendedCheck]
    required_tools: list[str]
    safety_warnings: list[str]
    supporting_evidence: list[SupportingEvidence]
    confidence: float
    urgency: Literal["low", "medium", "high"]
    escalate_if: list[str]
    follow_up_question: str | None = None

    @model_validator(mode="after")
    def validate_citations(self) -> CopilotAnswer:
        known = {e.citation_id for e in self.supporting_evidence}
        for check in self.recommended_checks:
            missing = [citation for citation in check.citations if citation not in known]
            if missing:
                raise ValueError(
                    f"recommended check cites unknown evidence ids: {', '.join(sorted(missing))}"
                )
        return self


class AnswerEnvelope(BaseModel):
    session_id: str
    tenant_id: str
    answer: CopilotAnswer


class CreateSessionRequest(BaseModel):
    machine_id: str
    site_id: str
    machine_model: str
    machine_family: str | None = None
    criticality: Literal["low", "medium", "high"] = "medium"
    work_order_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    tenant_id: str | None = None


class ManualPageSeed(BaseModel):
    page: int
    text: str = ""
    section_path: list[str] = Field(default_factory=list)
    table_rows: list[dict[str, str]] = Field(default_factory=list)
    visual_summaries: list[str] = Field(default_factory=list)


class ParsedManualPage(BaseModel):
    page: int
    text: str = ""
    section_path: list[str] = Field(default_factory=list)
    table_rows: list[dict[str, str]] = Field(default_factory=list)
    visual_summaries: list[str] = Field(default_factory=list)
    text_confidence: float = 1.0
    ocr_applied: bool = False


class IngestManualRequest(BaseModel):
    doc_id: str
    manufacturer: str
    machine_model: str
    machine_family: str | None = None
    manual_version: str
    pdf_path: str | None = None
    pages: list[ManualPageSeed] = Field(default_factory=list)
    activate_version: bool = True
    tenant_id: str | None = None


class ManualIngestJobRecord(BaseModel):
    job_id: str
    tenant_id: str
    status: ManualIngestJobStatus
    request: IngestManualRequest
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: int = 0
    error_message: str | None = None
    result: dict[str, Any] | None = None


class IngestLogRequest(BaseModel):
    machine_id: str
    site_id: str
    machine_model: str
    machine_family: str | None = None
    timestamp: datetime | None = None
    path: str
    markdown: str
    resolution_status: str = "resolved"
    tenant_id: str | None = None


class AnswerRequest(BaseModel):
    message: str
    machine_id: str
    site_id: str | None = None
    machine_model: str | None = None
    machine_family: str | None = None
    criticality: Literal["low", "medium", "high"] = "medium"
    session_id: str | None = None
    work_order_id: str | None = None
    measurements: dict[str, Any] = Field(default_factory=dict)
    completed_checks: list[str] = Field(default_factory=list)
    tenant_id: str | None = None


class IngestResult(BaseModel):
    corpus: Literal["oem_manuals", "historical_insights"]
    namespace: str
    chunk_count: int
    chunk_ids: list[str]


class NormalizedIncident(BaseModel):
    summary_text: str
    component: list[str] = Field(default_factory=list)
    issue_type: list[str] = Field(default_factory=list)
    candidate_fields: dict[str, Any] = Field(default_factory=dict)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    method: str = "rules"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
