from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

import httpx
import jwt
from pydantic import BaseModel

from maintenance_copilot.answering import (
    build_direct_information_answer,
    build_information_follow_up,
    is_informational_query,
    select_answer_evidence,
)
from maintenance_copilot.config import Settings
from maintenance_copilot.domain import (
    AssetMetadata,
    CopilotAnswer,
    KnowledgeChunk,
    NormalizedIncident,
    ParsedManualPage,
    RetrievedChunk,
    SessionState,
    SupportingEvidence,
    SuspectedCause,
    VerifiedIdentity,
)

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_/\-.]+")
IDENTIFIER_RE = re.compile(r"[A-Z]{1,6}\d{1,6}|[A-Za-z0-9-]{5,}")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class TextEmbedder(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class Reranker(Protocol):
    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        top_n: int,
        *,
        safety_critical: bool = False,
    ) -> list[RetrievedChunk]:
        ...


class VectorStore(Protocol):
    def upsert(
        self,
        corpus: str,
        namespace: str,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        ...

    def query(
        self,
        corpus: str,
        namespace: str,
        vector: Sequence[float],
        *,
        filter: dict[str, Any],
        top_k: int,
        sparse_terms: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        ...


class IncidentNormalizer(Protocol):
    def normalize(self, markdown: str) -> NormalizedIncident:
        ...


class ManualLayoutParser(Protocol):
    def parse_pdf(self, pdf_path: str) -> list[ParsedManualPage]:
        ...


class VisualSummarizer(Protocol):
    def summarize_page(self, image_bytes: bytes, page_context: str) -> list[str]:
        ...


class AnswerGenerator(Protocol):
    def generate(
        self,
        *,
        user_text: str,
        asset: AssetMetadata,
        state: SessionState,
        evidence: Sequence[RetrievedChunk],
        safety_critical: bool = False,
    ) -> CopilotAnswer:
        ...


class TokenVerifier(Protocol):
    def verify(self, token: str | None) -> VerifiedIdentity:
        ...


@dataclass(slots=True)
class _StoredVector:
    chunk: KnowledgeChunk
    embedding: list[float]
    tokens: set[str]


class HashedSparseEncoder:
    def __init__(self, dimension: int = 2**18) -> None:
        self.dimension = dimension

    def encode_text(self, text: str) -> dict[str, list[float] | list[int]]:
        weights: dict[int, float] = defaultdict(float)
        for token in tokenize(text):
            bucket = self._bucket(token)
            weights[bucket] += 1.0
        for token in IDENTIFIER_RE.findall(text):
            bucket = self._bucket(token.lower())
            weights[bucket] += 2.0
        return {
            "indices": list(weights.keys()),
            "values": list(weights.values()),
        }

    def encode_terms(self, terms: Sequence[str]) -> dict[str, list[float] | list[int]]:
        weights: dict[int, float] = defaultdict(float)
        for term in terms:
            bucket = self._bucket(term)
            weights[bucket] += 1.0
        return {
            "indices": list(weights.keys()),
            "values": list(weights.values()),
        }

    def _bucket(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % self.dimension


class HashTextEmbedder:
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


class HeuristicReranker:
    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        top_n: int,
        *,
        safety_critical: bool = False,
    ) -> list[RetrievedChunk]:
        query_terms = set(tokenize(query))
        reranked: list[RetrievedChunk] = []
        for candidate in candidates:
            overlap = len(query_terms.intersection(tokenize(candidate.chunk.text)))
            confidence_bonus = candidate.chunk.content_confidence * 0.2
            authority_bonus = 0.15 if candidate.chunk.is_manual else 0.0
            safety_bonus = 0.1 if safety_critical and candidate.chunk.is_manual else 0.0
            score = (
                candidate.score
                + (overlap * 0.08)
                + confidence_bonus
                + authority_bonus
                + safety_bonus
            )
            reranked.append(candidate.model_copy(update={"rerank_score": score}))
        reranked.sort(key=lambda item: item.blended_score, reverse=True)
        return reranked[:top_n]


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, list[_StoredVector]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def upsert(
        self,
        corpus: str,
        namespace: str,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        entries = self._store[corpus][namespace]
        existing = {entry.chunk.chunk_id: index for index, entry in enumerate(entries)}
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            stored = _StoredVector(
                chunk=chunk,
                embedding=list(embedding),
                tokens=set(tokenize(chunk.text)),
            )
            if chunk.chunk_id in existing:
                entries[existing[chunk.chunk_id]] = stored
            else:
                entries.append(stored)

    def query(
        self,
        corpus: str,
        namespace: str,
        vector: Sequence[float],
        *,
        filter: dict[str, Any],
        top_k: int,
        sparse_terms: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        sparse = set(sparse_terms or [])
        matches: list[RetrievedChunk] = []
        for entry in self._store[corpus].get(namespace, []):
            if not self._matches_filter(entry.chunk, filter):
                continue
            dense_score = cosine_similarity(vector, entry.embedding)
            lexical_score = len(sparse.intersection(entry.tokens)) * 0.05
            score = dense_score + lexical_score
            matches.append(
                RetrievedChunk(
                    chunk=entry.chunk,
                    corpus=corpus,  # type: ignore[arg-type]
                    score=score,
                )
            )
        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:top_k]

    def _matches_filter(self, chunk: KnowledgeChunk, filter: dict[str, Any]) -> bool:
        for key, expected in filter.items():
            actual = getattr(chunk, key, None)
            if expected is None:
                continue
            if isinstance(expected, list):
                if isinstance(actual, list):
                    if not set(actual).intersection(expected):
                        return False
                elif actual not in expected:
                    return False
                continue
            if isinstance(actual, list):
                if expected not in actual:
                    return False
                continue
            if actual != expected:
                return False
        return True


class StaticTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify(self, token: str | None) -> VerifiedIdentity:
        if token and token.startswith("dev:"):
            payload = token.removeprefix("dev:")
            subject, _, tenant_id = payload.partition("@")
            return VerifiedIdentity(
                subject=subject or self.settings.dev_user_id,
                tenant_id=tenant_id or self.settings.dev_tenant_id,
                raw_claims={"mode": "dev"},
            )
        return VerifiedIdentity(
            subject=self.settings.dev_user_id,
            tenant_id=self.settings.dev_tenant_id,
            raw_claims={"mode": "dev-default"},
        )


class OktaJWTVerifier:
    def __init__(self, issuer: str, audience: str) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self._jwks_client: jwt.PyJWKClient | None = None

    def verify(self, token: str | None) -> VerifiedIdentity:
        if not token:
            raise ValueError("missing bearer token")
        if self._jwks_client is None:
            config = httpx.get(
                f"{self.issuer}/.well-known/openid-configuration",
                timeout=10.0,
            ).json()
            self._jwks_client = jwt.PyJWKClient(config["jwks_uri"])
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
        )
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise ValueError("verified token missing tenant_id claim")
        return VerifiedIdentity(
            subject=payload["sub"],
            tenant_id=tenant_id,
            raw_claims=payload,
        )


class VertexTextEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=self.settings.google_project,
            location=self.settings.google_location,
        )
        response = client.models.embed_content(
            model=self.settings.text_embedding_model,
            contents=[text],
            config=types.EmbedContentConfig(
                output_dimensionality=self.settings.text_embedding_dimensions,
            ),
        )
        return list(response.embeddings[0].values)


class GeminiIncidentNormalizer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def normalize(self, markdown: str) -> NormalizedIncident:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=self.settings.google_project,
            location=self.settings.google_location,
        )
        prompt = (
            "Normalize this technician incident log into a reliable summary. "
            "Do not invent fields. Use low confidence when uncertain.\n\n"
            f"{markdown}"
        )
        response = client.models.generate_content(
            model=self.settings.generation_flash_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=NormalizedIncident,
                temperature=0.0,
            ),
        )
        if response.parsed:
            return NormalizedIncident.model_validate(response.parsed)
        return NormalizedIncident(summary_text=markdown[:200], method="rules_then_small_llm")


class GeminiVisualSummarizer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def summarize_page(self, image_bytes: bytes, page_context: str) -> list[str]:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=self.settings.google_project,
            location=self.settings.google_location,
        )
        prompt = (
            "Summarize the visually important maintenance-relevant content on this manual page. "
            "Return short semantic retrieval statements only."
        )
        response = client.models.generate_content(
            model=self.settings.generation_flash_model,
            contents=[
                prompt,
                page_context[:1200],
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[str],
                temperature=0.1,
            ),
        )
        if response.parsed:
            return list(response.parsed)[: self.settings.visual_summary_max_items]
        if response.text:
            return [line.strip("- ").strip() for line in response.text.splitlines() if line.strip()]
        return []


class _GeminiAnswerDraft(BaseModel):
    issue_summary: str
    suspected_causes: list[SuspectedCause]
    recommended_checks: list[dict[str, Any]]
    required_tools: list[str]
    safety_warnings: list[str]
    confidence: float
    urgency: Literal["low", "medium", "high"]
    escalate_if: list[str]
    follow_up_question: str | None = None


class GeminiAnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        *,
        user_text: str,
        asset: AssetMetadata,
        state: SessionState,
        evidence: Sequence[RetrievedChunk],
        safety_critical: bool = False,
    ) -> CopilotAnswer:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=self.settings.google_project,
            location=self.settings.google_location,
        )

        informational_query = is_informational_query(user_text)
        selected_evidence = select_answer_evidence(user_text, evidence)
        supporting: list[SupportingEvidence] = []
        manual_citation_ids: set[str] = set()
        manual_evidence = [item for item in selected_evidence if item.chunk.is_manual]
        for index, item in enumerate(selected_evidence, start=1):
            prefix = "M" if item.chunk.is_manual else "L"
            citation_id = f"{prefix}{index}"
            supporting.append(
                SupportingEvidence(
                    citation_id=citation_id,
                    source_type=item.chunk.source_family,
                    citation=item.chunk.citation(),
                    excerpt=item.chunk.excerpt(),
                )
            )
            if item.chunk.is_manual:
                manual_citation_ids.add(citation_id)

        evidence_payload = [
            {
                "citation_id": support.citation_id,
                "source_type": support.source_type,
                "citation": support.citation,
                "excerpt": support.excerpt,
            }
            for support in supporting
        ]
        system_instruction = (
            "You are a maintenance troubleshooting copilot. "
            "OEM manual evidence is authoritative for procedure and safety. "
            "Historical logs are contextual only. "
            "Every recommended check must cite at least one citation_id. "
            "If there is no OEM support for a procedure, do not propose that procedure."
        )
        if informational_query:
            system_instruction += (
                " For definition, explanation, or summary questions, answer directly in issue_summary. "
                "Do not describe the user's intent. "
                "Do not force suspected causes, escalation, or troubleshooting steps unless the user explicitly asks for a procedure. "
                "If the loaded manual evidence does not answer the question, say that directly."
            )
        contents = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "user_text": user_text,
                                "asset": asset.model_dump(mode="json"),
                                "session_state": state.model_dump(mode="json"),
                                "evidence": evidence_payload,
                            }
                        )
                    }
                ],
            }
        ]

        def call_model(model_name: str) -> _GeminiAnswerDraft:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=_GeminiAnswerDraft,
                    temperature=0.1,
                ),
            )
            if not response.parsed:
                raise ValueError("Gemini returned no structured answer")
            return _GeminiAnswerDraft.model_validate(response.parsed)

        draft = call_model(self.settings.generation_flash_model)
        if safety_critical and draft.confidence < self.settings.low_confidence_threshold:
            draft = call_model(self.settings.generation_pro_model)

        checks = []
        for raw_check in draft.recommended_checks:
            citations = [item for item in raw_check.get("citations", []) if item]
            if not citations:
                continue
            if not any(citation in manual_citation_ids for citation in citations):
                continue
            checks.append(raw_check)

        if informational_query:
            return CopilotAnswer(
                issue_summary=build_direct_information_answer(
                    user_text=user_text,
                    manual_evidence=manual_evidence,
                    candidate_answer=draft.issue_summary,
                ),
                suspected_causes=[],
                recommended_checks=[],
                required_tools=[],
                safety_warnings=draft.safety_warnings if manual_evidence else [],
                supporting_evidence=supporting,
                confidence=self._information_confidence(manual_evidence, draft.confidence),
                urgency="low",
                escalate_if=[],
                follow_up_question=(
                    draft.follow_up_question
                    if draft.follow_up_question and not draft.follow_up_question.lower().startswith("what symptom")
                    else build_information_follow_up(user_text, manual_evidence)
                ),
            )

        if not checks:
            return CopilotAnswer(
                issue_summary=draft.issue_summary or user_text,
                suspected_causes=draft.suspected_causes,
                recommended_checks=[],
                required_tools=draft.required_tools,
                safety_warnings=list(
                    dict.fromkeys(
                        [
                            *draft.safety_warnings,
                            "No OEM-backed procedural step passed citation validation.",
                        ]
                    )
                ),
                supporting_evidence=supporting,
                confidence=min(draft.confidence, 0.4),
                urgency=draft.urgency,
                escalate_if=list(
                    dict.fromkeys(
                        [
                            *draft.escalate_if,
                            "Manual evidence does not support a safe procedural recommendation.",
                        ]
                    )
                ),
                follow_up_question=draft.follow_up_question,
            )

        return CopilotAnswer(
            issue_summary=draft.issue_summary or user_text,
            suspected_causes=draft.suspected_causes,
            recommended_checks=checks,
            required_tools=draft.required_tools,
            safety_warnings=draft.safety_warnings,
            supporting_evidence=supporting,
            confidence=draft.confidence,
            urgency=draft.urgency,
            escalate_if=draft.escalate_if,
            follow_up_question=draft.follow_up_question,
        )

    def _information_confidence(
        self,
        manual_evidence: Sequence[RetrievedChunk],
        draft_confidence: float,
    ) -> float:
        if not manual_evidence:
            return min(draft_confidence, 0.25)
        evidence_scores = [
            min(max(item.blended_score, 0.25), 1.0)
            for item in manual_evidence[:3]
        ]
        evidence_confidence = sum(evidence_scores) / len(evidence_scores)
        return round((evidence_confidence + max(draft_confidence, 0.35)) / 2, 2)


class DocumentAiLayoutParser:
    DOCAI_PAGE_LIMIT = 30
    DOCAI_OCR_PAGE_LIMIT = 15

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def parse_pdf(self, pdf_path: str) -> list[ParsedManualPage]:
        from google.cloud import documentai

        document_bytes = Path(pdf_path).read_bytes()
        client = documentai.DocumentProcessorServiceClient(
            client_options={
                "api_endpoint": f"{self.settings.documentai_location}-documentai.googleapis.com"
            }
        )
        processor_name = self._processor_name(self.settings.documentai_layout_processor_id)
        chunks_list = self._pdf_chunks(document_bytes)
        logger.info("parse_pdf: %d page chunks to process", len(chunks_list))
        pages: list[ParsedManualPage] = []
        for chunk_index, (page_offset, chunk_bytes) in enumerate(chunks_list):
            response = client.process_document(
                request=documentai.ProcessRequest(
                    name=processor_name,
                    raw_document=documentai.RawDocument(
                        content=chunk_bytes,
                        mime_type="application/pdf",
                    ),
                )
            )
            doc = response.document
            logger.info(
                "parse_pdf chunk %d: document.text length=%d, pages=%d",
                chunk_index,
                len(doc.text or ""),
                len(doc.pages),
            )
            chunk_pages = self._extract_pages(doc)
            for p in chunk_pages:
                p.page += page_offset
                pages.append(p)

        text_pages = sum(1 for p in pages if p.text.strip())
        logger.info(
            "parse_pdf: %d total pages, %d with text",
            len(pages),
            text_pages,
        )
        needs_ocr = any(
            len(page.text.strip()) < self.settings.manual_visual_low_text_threshold
            for page in pages
        )
        if self.settings.documentai_ocr_processor_id and needs_ocr:
            ocr_pages = self._run_ocr(document_bytes)
            page_by_number = {page.page: page for page in ocr_pages}
            for page in pages:
                if len(page.text.strip()) < self.settings.manual_visual_low_text_threshold:
                    ocr_page = page_by_number.get(page.page)
                    if ocr_page and ocr_page.text:
                        page.text = ocr_page.text
                        page.text_confidence = max(page.text_confidence, ocr_page.text_confidence)
                        page.ocr_applied = True
        return pages

    def _run_ocr(self, document_bytes: bytes) -> list[ParsedManualPage]:
        from google.cloud import documentai

        client = documentai.DocumentProcessorServiceClient(
            client_options={
                "api_endpoint": f"{self.settings.documentai_location}-documentai.googleapis.com"
            }
        )
        processor_name = self._processor_name(self.settings.documentai_ocr_processor_id)
        pages: list[ParsedManualPage] = []
        for page_offset, chunk_bytes in self._pdf_chunks(
            document_bytes, page_limit=self.DOCAI_OCR_PAGE_LIMIT
        ):
            response = client.process_document(
                request=documentai.ProcessRequest(
                    name=processor_name,
                    raw_document=documentai.RawDocument(
                        content=chunk_bytes,
                        mime_type="application/pdf",
                    ),
                )
            )
            for p in self._extract_pages(response.document):
                p.page += page_offset
                pages.append(p)
        return pages

    def _pdf_chunks(
        self, pdf_bytes: bytes, *, page_limit: int | None = None,
    ) -> list[tuple[int, bytes]]:
        """Split PDF bytes into chunks of at most *page_limit* pages.

        Returns (page_offset, chunk_bytes) tuples where page_offset is the
        0-based index of the first page in the chunk (so _extract_pages results
        starting at 1 can be shifted to the global page number).
        """
        import fitz

        limit = page_limit or self.DOCAI_PAGE_LIMIT
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total = doc.page_count
        if total <= limit:
            doc.close()
            return [(0, pdf_bytes)]

        chunks: list[tuple[int, bytes]] = []
        for start in range(0, total, limit):
            end = min(start + limit, total)
            sub = fitz.open()
            sub.insert_pdf(doc, from_page=start, to_page=end - 1)
            chunks.append((start, sub.tobytes()))
            sub.close()
        doc.close()
        return chunks

    def _processor_name(self, processor_id: str | None) -> str:
        if not processor_id:
            raise ValueError("Document AI processor id is required")
        if "/processors/" in processor_id:
            return processor_id
        return (
            f"projects/{self.settings.google_project}/locations/{self.settings.documentai_location}/"
            f"processors/{processor_id}"
        )

    def _extract_pages(self, document) -> list[ParsedManualPage]:
        layout = getattr(document, "document_layout", None)
        if layout and layout.blocks:
            return self._extract_pages_from_layout(layout)
        return self._extract_pages_from_document(document)

    # -- Layout Parser format (document.document_layout) ------------------

    def _extract_pages_from_layout(self, layout) -> list[ParsedManualPage]:
        page_texts: dict[int, list[str]] = defaultdict(list)
        page_sections: dict[int, list[str]] = defaultdict(list)
        page_tables: dict[int, list[dict[str, str]]] = defaultdict(list)

        for block in layout.blocks:
            self._walk_layout_block(block, page_texts, page_sections, page_tables)

        if not page_texts and not page_tables:
            return []

        all_pages = sorted(set(page_texts) | set(page_tables))
        pages: list[ParsedManualPage] = []
        for page_num in all_pages:
            text = "\n\n".join(page_texts.get(page_num, []))
            section = page_sections.get(page_num, ["Document", f"Page {page_num}"])
            pages.append(
                ParsedManualPage(
                    page=page_num,
                    text=text,
                    section_path=section[:2] if section else ["Document", f"Page {page_num}"],
                    table_rows=page_tables.get(page_num, []),
                    text_confidence=0.95 if text.strip() else 0.2,
                )
            )
        return pages

    def _walk_layout_block(
        self,
        block,
        page_texts: dict[int, list[str]],
        page_sections: dict[int, list[str]],
        page_tables: dict[int, list[dict[str, str]]],
    ) -> None:
        page_num = self._block_page(block)

        if block.text_block:
            tb = block.text_block
            text = (tb.text or "").strip()
            block_type = tb.type_ or ""
            if text and block_type != "footer":
                page_texts[page_num].append(text)
                if "heading" in block_type and not page_sections.get(page_num):
                    page_sections[page_num] = [text]
                elif "heading" in block_type and len(page_sections[page_num]) < 2:
                    page_sections[page_num].append(text)
            for child in tb.blocks:
                self._walk_layout_block(child, page_texts, page_sections, page_tables)

        elif block.table_block:
            tbl = block.table_block
            headers: list[str] = []
            for hrow in getattr(tbl, "header_rows", []):
                headers = [
                    self._table_cell_text(cell) for cell in getattr(hrow, "cells", [])
                ]
                break
            for brow in getattr(tbl, "body_rows", []):
                values = [
                    self._table_cell_text(cell) for cell in getattr(brow, "cells", [])
                ]
                if not any(values):
                    continue
                if headers and len(headers) == len(values):
                    page_tables[page_num].append(dict(zip(headers, values, strict=True)))
                else:
                    page_tables[page_num].append(
                        {f"col_{i + 1}": v for i, v in enumerate(values)}
                    )

        elif block.list_block:
            for entry in block.list_block.list_entries:
                for child in entry.blocks:
                    self._walk_layout_block(child, page_texts, page_sections, page_tables)

    @staticmethod
    def _block_page(block) -> int:
        span = getattr(block, "page_span", None)
        if span and span.page_start:
            return span.page_start
        return 1

    @staticmethod
    def _table_cell_text(cell) -> str:
        parts: list[str] = []
        for block in getattr(cell, "blocks", []):
            if block.text_block and block.text_block.text:
                parts.append(block.text_block.text.strip())
        return " ".join(parts)

    # -- Classic format (document.pages) -----------------------------------

    def _extract_pages_from_document(self, document) -> list[ParsedManualPage]:
        pages: list[ParsedManualPage] = []
        full_text = document.text or ""
        for page_number, page in enumerate(document.pages, start=1):
            paragraph_texts = [
                self._layout_text(full_text, paragraph.layout)
                for paragraph in getattr(page, "paragraphs", [])
            ]
            page_text = "\n\n".join(text for text in paragraph_texts if text.strip())
            if not page_text.strip():
                block_texts = [
                    self._layout_text(full_text, block.layout)
                    for block in getattr(page, "blocks", [])
                ]
                page_text = "\n\n".join(text for text in block_texts if text.strip())
            table_rows = self._extract_table_rows(full_text, getattr(page, "tables", []))
            pages.append(
                ParsedManualPage(
                    page=page_number,
                    text=page_text,
                    section_path=self._infer_section_path(page_text, page_number),
                    table_rows=table_rows,
                    text_confidence=0.95 if page_text.strip() else 0.2,
                )
            )
        return pages

    def _extract_table_rows(self, full_text: str, tables) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for table in tables:
            header = self._row_text(full_text, getattr(table, "header_rows", []))
            for row in getattr(table, "body_rows", []):
                values = [
                    self._layout_text(full_text, cell.layout)
                    for cell in getattr(row, "cells", [])
                ]
                if not any(values):
                    continue
                if header and len(header) == len(values):
                    rows.append(dict(zip(header, values, strict=True)))
                else:
                    rows.append({f"col_{index + 1}": value for index, value in enumerate(values)})
        return rows

    def _row_text(self, full_text: str, rows) -> list[str]:
        if not rows:
            return []
        return [
            self._layout_text(full_text, cell.layout)
            for cell in getattr(rows[0], "cells", [])
        ]

    def _layout_text(self, full_text: str, layout) -> str:
        text_anchor = getattr(layout, "text_anchor", None)
        if not text_anchor or not text_anchor.text_segments:
            return ""
        chunks = []
        for segment in text_anchor.text_segments:
            start = getattr(segment, "start_index", 0) or 0
            end = getattr(segment, "end_index", 0) or 0
            chunks.append(full_text[start:end])
        return "".join(chunks).strip()

    def _infer_section_path(self, text: str, page_number: int) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        headings = [line for line in lines[:5] if line == line.upper() or line.endswith(":")]
        if headings[:2]:
            return headings[:2]
        if headings:
            return ["Document", headings[0]]
        return ["Document", f"Page {page_number}"]


class VertexRankingReranker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._credentials = None

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        top_n: int,
        *,
        safety_critical: bool = False,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        model = (
            self.settings.ranking_model_default
            if safety_critical
            else self.settings.ranking_model_fast
        )
        response = httpx.post(
            self._endpoint(),
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": self.settings.google_project or "",
            },
            json={
                "model": model,
                "topN": top_n,
                "query": query,
                "records": [
                    self._record_payload(candidate)
                    for candidate in candidates
                ],
            },
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        ranked_records = response.json().get("records", [])

        by_chunk_id = {candidate.chunk.chunk_id: candidate for candidate in candidates}
        reordered: list[RetrievedChunk] = []
        for record in ranked_records:
            candidate = by_chunk_id.get(record.get("id"))
            if candidate is None:
                continue
            reordered.append(
                candidate.model_copy(
                    update={"rerank_score": float(record.get("score", candidate.score))}
                )
            )

        seen = {candidate.chunk.chunk_id for candidate in reordered}
        for candidate in candidates:
            if candidate.chunk.chunk_id in seen:
                continue
            reordered.append(candidate)
            seen.add(candidate.chunk.chunk_id)
            if len(reordered) >= top_n:
                break
        return reordered[:top_n]

    def _access_token(self) -> str:
        import google.auth
        from google.auth.transport.requests import Request

        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not self._credentials.valid or self._credentials.expired or not self._credentials.token:
            self._credentials.refresh(Request())
        return str(self._credentials.token)

    def _endpoint(self) -> str:
        if not self.settings.google_project:
            raise ValueError("COPILOT_GOOGLE_PROJECT is required for Vertex ranking")
        return (
            "https://discoveryengine.googleapis.com/v1/"
            f"projects/{self.settings.google_project}/locations/{self.settings.ranking_location}/"
            f"rankingConfigs/{self.settings.ranking_config}:rank"
        )

    def _record_payload(self, candidate: RetrievedChunk) -> dict[str, str]:
        chunk = candidate.chunk
        title = self._title(chunk)
        content = json.dumps(
            {
                "text": chunk.text,
                "source_type": chunk.source_type.value,
                "machine_model": chunk.machine_model,
                "machine_family": chunk.machine_family,
                "manual_version": chunk.manual_version,
                "section_path": chunk.section_path,
                "citation": chunk.citation(),
            },
            ensure_ascii=True,
        )
        return {
            "id": chunk.chunk_id,
            "title": title,
            "content": content,
        }

    def _title(self, chunk: KnowledgeChunk) -> str:
        if chunk.is_manual and chunk.section_path:
            return " > ".join(chunk.section_path[-2:])
        if chunk.machine_id:
            return f"{chunk.machine_id} {chunk.source_type.value}"
        return chunk.source_type.value


class PineconeVectorStore:
    def __init__(self, settings: Settings) -> None:
        from pinecone import Pinecone

        self._settings = settings
        self._client = Pinecone(api_key=settings.pinecone_api_key)
        self._indexes = {
            "oem_manuals": self._client.Index(settings.pinecone_manual_index),
            "historical_insights": self._client.Index(settings.pinecone_log_index),
        }
        self._sparse_encoder = HashedSparseEncoder()

    def upsert(
        self,
        corpus: str,
        namespace: str,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        index = self._indexes[corpus]
        vectors = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            metadata = {
                k: v for k, v in chunk.metadata().items() if v is not None
            }
            metadata["chunk"] = json.dumps(chunk.model_dump(mode="json"))
            sparse_values = self._sparse_encoder.encode_text(chunk.text)
            vec: dict[str, Any] = {
                "id": chunk.chunk_id,
                "values": list(embedding),
                "metadata": metadata,
            }
            if sparse_values and sparse_values.get("indices"):
                vec["sparse_values"] = sparse_values
            vectors.append(vec)
        if not vectors:
            return
        batch_size = 50
        for i in range(0, len(vectors), batch_size):
            index.upsert(vectors=vectors[i : i + batch_size], namespace=namespace)

    def query(
        self,
        corpus: str,
        namespace: str,
        vector: Sequence[float],
        *,
        filter: dict[str, Any],
        top_k: int,
        sparse_terms: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        index = self._indexes[corpus]
        sparse_vector = None
        if sparse_terms:
            sparse_vector = self._sparse_encoder.encode_terms(sparse_terms)
        response = index.query(
            namespace=namespace,
            vector=list(vector),
            sparse_vector=sparse_vector,
            filter={key: value for key, value in filter.items() if value is not None},
            top_k=top_k,
            include_metadata=True,
        )
        results: list[RetrievedChunk] = []
        matches = response.get("matches", []) if isinstance(response, dict) else response.matches
        for match in matches:
            metadata = match["metadata"] if isinstance(match, dict) else match.metadata
            score = match["score"] if isinstance(match, dict) else match.score
            raw = metadata["chunk"]
            chunk = KnowledgeChunk.model_validate(
                json.loads(raw) if isinstance(raw, str) else raw
            )
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    corpus=corpus,  # type: ignore[arg-type]
                    score=float(score),
                )
            )
        return results
