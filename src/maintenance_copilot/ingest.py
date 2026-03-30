from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from maintenance_copilot.domain import (
    ChunkSourceType,
    ExcerptRef,
    ExtractionMetadata,
    IngestLogRequest,
    IngestManualRequest,
    IngestResult,
    KnowledgeChunk,
    ManualIngestJobRecord,
    NormalizedIncident,
    ParsedManualPage,
    SourceRef,
)
from maintenance_copilot.providers import (
    IncidentNormalizer,
    ManualLayoutParser,
    TextEmbedder,
    VectorStore,
    VisualSummarizer,
)
from maintenance_copilot.sessions import ManualBindingRepository, ManualIngestJobRepository

TIMESTAMP_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)Z?)?\b")
MACHINE_RE = re.compile(r"\b([A-Za-z]{1,4}\d{1,4})\b")
FAULT_RE = re.compile(r"\b(?:fault|code)\s*[:#-]?\s*([A-Z]?\d{2,5})\b", re.IGNORECASE)
PART_RE = re.compile(r"\b(?:part|pn|p\/n)\s*[:#-]?\s*([A-Z0-9-]{3,})\b", re.IGNORECASE)


class ManualIngestPipeline:
    def __init__(
        self,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        *,
        parser: ManualLayoutParser | None = None,
        visual_summarizer: VisualSummarizer | None = None,
        binding_repo: ManualBindingRepository | None = None,
        visual_low_text_threshold: int = 80,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.parser = parser
        self.visual_summarizer = visual_summarizer
        self.binding_repo = binding_repo
        self.visual_low_text_threshold = visual_low_text_threshold

    def ingest(self, request: IngestManualRequest, tenant_id: str) -> IngestResult:
        pages = self._prepare_pages(request)
        logger.info(
            "ingest: %d pages, text lengths: %s",
            len(pages),
            [len(p.text) for p in pages[:10]],
        )
        chunks: list[KnowledgeChunk] = []
        for page in pages:
            section_path = page.section_path or ["Document", f"Page {page.page}"]
            for index, paragraph in enumerate(self._paragraphs(page.text), start=1):
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=(
                            f"manual:{request.machine_model}:{request.manual_version}:"
                            f"p{page.page}:sec:{index}"
                        ),
                        tenant_id=tenant_id,
                        source_type=ChunkSourceType.OEM_MANUAL_SECTION,
                        manufacturer=request.manufacturer,
                        machine_model=request.machine_model,
                        machine_family=request.machine_family,
                        manual_version=request.manual_version,
                        page=page.page,
                        section_path=section_path,
                        text=paragraph,
                        source_ref=SourceRef(
                            doc_id=request.doc_id,
                            page=page.page,
                            link=f"{request.doc_id}#page={page.page}",
                        ),
                        content_confidence=page.text_confidence,
                    )
                )
            for row_index, row in enumerate(page.table_rows, start=1):
                row_text = " | ".join(f"{key}: {value}" for key, value in row.items())
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=(
                            f"manual:{request.machine_model}:{request.manual_version}:"
                            f"p{page.page}:tbl:{row_index}"
                        ),
                        tenant_id=tenant_id,
                        source_type=ChunkSourceType.OEM_MANUAL_TABLE_ROW,
                        manufacturer=request.manufacturer,
                        machine_model=request.machine_model,
                        machine_family=request.machine_family,
                        manual_version=request.manual_version,
                        page=page.page,
                        section_path=section_path,
                        text=row_text,
                        structured_fields={key: value for key, value in row.items()},
                        source_ref=SourceRef(
                            doc_id=request.doc_id,
                            page=page.page,
                            table_id=f"tbl_p{page.page}_{row_index}",
                            row=row_index,
                            link=f"{request.doc_id}#page={page.page}",
                        ),
                        content_confidence=max(page.text_confidence - 0.05, 0.7),
                    )
                )
            for figure_index, summary in enumerate(page.visual_summaries, start=1):
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=(
                            f"manual:{request.machine_model}:{request.manual_version}:"
                            f"p{page.page}:fig:{figure_index}"
                        ),
                        tenant_id=tenant_id,
                        source_type=ChunkSourceType.OEM_MANUAL_FIGURE_SEMANTIC,
                        manufacturer=request.manufacturer,
                        machine_model=request.machine_model,
                        machine_family=request.machine_family,
                        manual_version=request.manual_version,
                        page=page.page,
                        section_path=section_path,
                        text=summary,
                        source_ref=SourceRef(
                            doc_id=request.doc_id,
                            page=page.page,
                            figure_id=f"fig_p{page.page}_{figure_index}",
                            link=f"{request.doc_id}#page={page.page}",
                        ),
                        content_confidence=max(page.text_confidence - 0.1, 0.6),
                    )
                )
        if chunks:
            embeddings = self.embedder.embed_texts([chunk.text for chunk in chunks])
            self.vector_store.upsert("oem_manuals", tenant_id, chunks, embeddings)
        if self.binding_repo and request.activate_version:
            self.binding_repo.upsert_active(
                tenant_id=tenant_id,
                machine_model=request.machine_model,
                machine_family=request.machine_family,
                doc_id=request.doc_id,
                manual_version=request.manual_version,
            )
        return IngestResult(
            corpus="oem_manuals",
            namespace=tenant_id,
            chunk_count=len(chunks),
            chunk_ids=[chunk.chunk_id for chunk in chunks],
        )

    def _prepare_pages(self, request: IngestManualRequest) -> list[ParsedManualPage]:
        if request.pages:
            return [
                ParsedManualPage(
                    page=page.page,
                    text=page.text,
                    section_path=page.section_path,
                    table_rows=page.table_rows,
                    visual_summaries=page.visual_summaries,
                    text_confidence=0.97,
                )
                for page in request.pages
            ]
        if request.pdf_path and self.parser:
            pages = self.parser.parse_pdf(request.pdf_path)
            if self.visual_summarizer:
                pages = self._add_visual_summaries(request.pdf_path, pages)
            return pages
        return self._load_pdf_pages(request.pdf_path)

    def _load_pdf_pages(self, pdf_path: str | None) -> list[ParsedManualPage]:
        if not pdf_path:
            return []
        import fitz

        pages: list[ParsedManualPage] = []
        document = fitz.open(pdf_path)
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            pages.append(
                ParsedManualPage(
                    page=page_number + 1,
                    text=page.get_text("text"),
                    section_path=["Document", f"Page {page_number + 1}"],
                    text_confidence=0.9,
                )
            )
        return pages

    def _add_visual_summaries(
        self,
        pdf_path: str,
        pages: list[ParsedManualPage],
    ) -> list[ParsedManualPage]:
        import fitz

        document = fitz.open(pdf_path)
        enriched: list[ParsedManualPage] = []
        for page in pages:
            should_summarize = (
                len(page.text.strip()) < self.visual_low_text_threshold or bool(page.table_rows)
            )
            if not should_summarize:
                enriched.append(page)
                continue
            pixmap = document.load_page(page.page - 1).get_pixmap(dpi=150)
            summaries = self.visual_summarizer.summarize_page(
                pixmap.tobytes("png"),
                page.text[:1200],
            )
            enriched.append(
                page.model_copy(
                    update={
                        "visual_summaries": [
                            *page.visual_summaries,
                            *summaries,
                        ][:3]
                    }
                )
            )
        return enriched

    def _paragraphs(self, text: str, max_chars: int = 450) -> list[str]:
        parts = [part.strip() for part in text.split("\n\n") if part.strip()]
        paragraphs: list[str] = []
        for part in parts:
            if len(part) <= max_chars:
                paragraphs.append(part)
                continue
            buffer = []
            current = ""
            for sentence in re.split(r"(?<=[.!?])\s+", part):
                if len(current) + len(sentence) + 1 <= max_chars:
                    current = f"{current} {sentence}".strip()
                else:
                    if current:
                        buffer.append(current)
                    current = sentence
            if current:
                buffer.append(current)
            paragraphs.extend(chunk for chunk in buffer if chunk)
        return paragraphs or ([text.strip()] if text.strip() else [])


class ManualIngestJobProcessor:
    def __init__(
        self,
        job_repo: ManualIngestJobRepository,
        manual_pipeline: ManualIngestPipeline,
    ) -> None:
        self.job_repo = job_repo
        self.manual_pipeline = manual_pipeline

    def process(self, job: ManualIngestJobRecord) -> ManualIngestJobRecord:
        try:
            result = self.manual_pipeline.ingest(job.request, job.tenant_id)
        except Exception as exc:
            return self.job_repo.mark_failed(job.job_id, str(exc))
        return self.job_repo.mark_success(
            job.job_id,
            result.model_dump(mode="json"),
        )


class LogIngestPipeline:
    def __init__(
        self,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        *,
        normalizer: IncidentNormalizer | None = None,
        confidence_threshold: float = 0.75,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.normalizer = normalizer
        self.confidence_threshold = confidence_threshold

    def ingest(self, request: IngestLogRequest, tenant_id: str) -> IngestResult:
        normalized = self._normalize(request)
        timestamp = (
            request.timestamp
            or self._extract_timestamp(request.markdown)
            or datetime.now(UTC)
        )
        machine_id = request.machine_id or self._extract_machine_id(request.markdown) or "unknown"
        slug = timestamp.date().isoformat()
        summary_chunk = KnowledgeChunk(
            chunk_id=f"log:{machine_id}:{slug}:summary",
            tenant_id=tenant_id,
            source_type=ChunkSourceType.HISTORICAL_INSIGHT,
            machine_id=machine_id,
            machine_model=request.machine_model,
            machine_family=request.machine_family,
            site_id=request.site_id,
            component=normalized.component,
            issue_type=normalized.issue_type,
            timestamp=timestamp,
            text=normalized.summary_text,
            extraction=ExtractionMetadata(
                method=normalized.method,
                field_confidence=normalized.field_confidence,
                candidate_fields=normalized.candidate_fields,
            ),
            resolution_status=request.resolution_status,
            source_ref=SourceRef(
                path=request.path,
                excerpt=self._summary_excerpt(request.markdown),
            ),
            content_confidence=max(normalized.field_confidence.values(), default=0.68),
        )
        chunks = [summary_chunk]
        for index, span in enumerate(self._evidence_spans(request.markdown), start=1):
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"log:{machine_id}:{slug}:span:{index}",
                    tenant_id=tenant_id,
                    source_type=ChunkSourceType.HISTORICAL_INSIGHT_SPAN,
                    parent_chunk_id=summary_chunk.chunk_id,
                    machine_id=machine_id,
                    machine_model=request.machine_model,
                    machine_family=request.machine_family,
                    site_id=request.site_id,
                    component=normalized.component,
                    issue_type=normalized.issue_type,
                    timestamp=timestamp,
                    text=str(span["text"]),
                    source_ref=SourceRef(path=request.path, excerpt=span["excerpt"]),
                    content_confidence=0.7,
                )
            )
        embeddings = self.embedder.embed_texts([chunk.text for chunk in chunks])
        self.vector_store.upsert("historical_insights", tenant_id, chunks, embeddings)
        return IngestResult(
            corpus="historical_insights",
            namespace=tenant_id,
            chunk_count=len(chunks),
            chunk_ids=[chunk.chunk_id for chunk in chunks],
        )

    def _normalize(self, request: IngestLogRequest) -> NormalizedIncident:
        lines = [line.strip() for line in request.markdown.splitlines() if line.strip()]
        machine_id = request.machine_id or self._extract_machine_id(request.markdown)
        fault_codes = FAULT_RE.findall(request.markdown)
        part_numbers = PART_RE.findall(request.markdown)
        components = self._extract_components(request.markdown)
        issues = self._extract_issues(request.markdown)
        resolution = self._extract_resolution(request.markdown)
        confidence = {
            "machine_id": 0.95 if machine_id else 0.2,
            "issue_type": 0.85 if issues else 0.35,
            "outcome": 0.8 if resolution else 0.3,
            "fault_codes": 0.8 if fault_codes else 0.2,
        }
        heuristic_score = (
            confidence["machine_id"] * 0.35
            + confidence["issue_type"] * 0.35
            + confidence["outcome"] * 0.2
            + confidence["fault_codes"] * 0.1
        )
        if heuristic_score < self.confidence_threshold and self.normalizer:
            normalized = self.normalizer.normalize(request.markdown)
            return normalized
        summary_parts = []
        if machine_id:
            summary_parts.append(machine_id.upper())
        if issues:
            summary_parts.append(", ".join(issues))
        if components:
            summary_parts.append(f"component: {', '.join(components)}")
        if fault_codes:
            summary_parts.append(f"fault code(s): {', '.join(fault_codes)}")
        if resolution:
            summary_parts.append(resolution)
        if not summary_parts and lines:
            summary_parts.append(lines[0])
        return NormalizedIncident(
            summary_text=". ".join(summary_parts),
            component=components,
            issue_type=issues,
            candidate_fields={
                "machine_id": machine_id,
                "fault_codes": fault_codes,
                "part_numbers": part_numbers,
            },
            field_confidence=confidence,
            method=(
                "rules"
                if heuristic_score >= self.confidence_threshold
                else "rules_then_small_llm"
            ),
        )

    def _extract_timestamp(self, markdown: str) -> datetime | None:
        match = TIMESTAMP_RE.search(markdown)
        if not match:
            return None
        date_part, time_part = match.groups()
        stamp = f"{date_part}T{time_part or '00:00:00'}+00:00"
        return datetime.fromisoformat(stamp)

    def _extract_machine_id(self, markdown: str) -> str | None:
        for candidate in MACHINE_RE.findall(markdown):
            if any(character.isdigit() for character in candidate):
                return candidate.lower()
        return None

    def _extract_components(self, markdown: str) -> list[str]:
        keywords = ["cooling_system", "filter", "fan", "bearing", "motor", "valve", "pump"]
        text = markdown.lower()
        return [
            keyword
            for keyword in keywords
            if keyword.replace("_", " ") in text or keyword in text
        ]

    def _extract_issues(self, markdown: str) -> list[str]:
        keywords = ["overheating", "vibration", "pressure_drop", "leak", "noise", "shutdown"]
        text = markdown.lower()
        issues = []
        for keyword in keywords:
            token = keyword.replace("_", " ")
            if token in text or keyword in text:
                issues.append(keyword)
        return issues

    def _extract_resolution(self, markdown: str) -> str | None:
        for line in markdown.splitlines():
            lower = line.lower()
            if any(
                token in lower
                for token in [
                    "restored",
                    "resolved",
                    "stable",
                    "restarted",
                    "replaced",
                    "cleaned",
                ]
            ):
                return line.strip()
        return None

    def _summary_excerpt(self, markdown: str) -> ExcerptRef | None:
        lines = [index for index, line in enumerate(markdown.splitlines(), start=1) if line.strip()]
        if not lines:
            return None
        return ExcerptRef(start_line=lines[0], end_line=lines[min(len(lines), 5) - 1])

    def _evidence_spans(self, markdown: str) -> list[dict[str, object]]:
        lines = markdown.splitlines()
        spans: list[dict[str, object]] = []
        interesting_tokens = ("found", "cleaned", "replaced", "stable", "blocked", "restarted")
        for index, line in enumerate(lines, start=1):
            if any(token in line.lower() for token in interesting_tokens):
                start = index
                end = min(index + 1, len(lines))
                text = " ".join(item.strip() for item in lines[start - 1 : end] if item.strip())
                spans.append(
                    {
                        "text": text,
                        "excerpt": ExcerptRef(start_line=start, end_line=end),
                    }
                )
        if spans:
            return spans
        non_empty = [
            (index, line.strip())
            for index, line in enumerate(lines, start=1)
            if line.strip()
        ]
        if not non_empty:
            return []
        start = non_empty[0][0]
        end = non_empty[min(2, len(non_empty) - 1)][0]
        text = " ".join(line for _, line in non_empty[:3])
        return [
            {
                "text": text,
                "excerpt": ExcerptRef(start_line=start, end_line=end),
            }
        ]


def load_manual_seed(path: str) -> IngestManualRequest:
    return IngestManualRequest.model_validate_json(Path(path).read_text())


def load_log_seed(path: str) -> IngestLogRequest:
    return IngestLogRequest.model_validate_json(Path(path).read_text())
