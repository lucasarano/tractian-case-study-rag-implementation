from __future__ import annotations

import os
from uuid import uuid4

import pytest

from maintenance_copilot.config import Settings
from maintenance_copilot.domain import ChunkSourceType, KnowledgeChunk, SourceRef
from maintenance_copilot.providers import (
    DocumentAiLayoutParser,
    PineconeVectorStore,
    VertexRankingReranker,
    VertexTextEmbedder,
)


def smoke_settings() -> Settings:
    return Settings()


@pytest.mark.skipif(
    not os.getenv("COPILOT_GOOGLE_PROJECT"),
    reason="Vertex smoke test requires Google credentials and project settings",
)
def test_vertex_embedder_smoke() -> None:
    settings = smoke_settings()
    embedder = VertexTextEmbedder(settings)
    vector = embedder.embed_query("maintenance overheating airflow obstruction")
    assert len(vector) == settings.text_embedding_dimensions


@pytest.mark.skipif(
    not (
        os.getenv("COPILOT_GOOGLE_PROJECT")
        and os.getenv("COPILOT_DOCUMENTAI_LAYOUT_PROCESSOR_ID")
        and os.getenv("COPILOT_SMOKE_MANUAL_PDF")
    ),
    reason="Document AI smoke test requires credentials, processor id, and a sample pdf",
)
def test_document_ai_layout_parser_smoke() -> None:
    settings = smoke_settings()
    parser = DocumentAiLayoutParser(settings)
    pages = parser.parse_pdf(os.environ["COPILOT_SMOKE_MANUAL_PDF"])
    assert pages
    assert any(page.text or page.table_rows for page in pages)


@pytest.mark.skipif(
    not os.getenv("COPILOT_GOOGLE_PROJECT"),
    reason="Vertex ranking smoke test requires Google credentials and project settings",
)
def test_vertex_ranking_reranker_smoke() -> None:
    from maintenance_copilot.domain import RetrievedChunk

    settings = smoke_settings()
    reranker = VertexRankingReranker(settings)
    candidates = [
        RetrievedChunk(
            chunk=KnowledgeChunk(
                chunk_id="manual:x200:v3:p184:sec:1",
                tenant_id="companyA",
                source_type=ChunkSourceType.OEM_MANUAL_SECTION,
                text="Inspect intake airflow path and clear any obstruction.",
                machine_model="x200",
                source_ref=SourceRef(doc_id="manual_x200_v3", page=184),
            ),
            corpus="oem_manuals",
            score=0.5,
        ),
        RetrievedChunk(
            chunk=KnowledgeChunk(
                chunk_id="log:mx17:2026-01-12:summary",
                tenant_id="companyA",
                source_type=ChunkSourceType.HISTORICAL_INSIGHT,
                text="Resolved overheating by cleaning clogged intake filter.",
                machine_model="x200",
                source_ref=SourceRef(path="logs/incident.md"),
            ),
            corpus="historical_insights",
            score=0.4,
        ),
    ]
    reranked = reranker.rerank(
        "MX17 overheating after 20 minutes. What should I check first?",
        candidates,
        top_n=2,
    )
    assert len(reranked) == 2
    assert reranked[0].rerank_score is not None


@pytest.mark.skipif(
    not (
        os.getenv("COPILOT_GOOGLE_PROJECT")
        and os.getenv("COPILOT_PINECONE_API_KEY")
        and os.getenv("COPILOT_PINECONE_MANUAL_INDEX")
    ),
    reason="Pinecone smoke test requires Google and Pinecone configuration",
)
def test_pinecone_vector_store_smoke() -> None:
    settings = smoke_settings()
    embedder = VertexTextEmbedder(settings)
    vector_store = PineconeVectorStore(settings)
    namespace = f"smoke-{uuid4().hex[:8]}"
    chunk = KnowledgeChunk(
        chunk_id=f"manual:x200:v3:p184:sec:{uuid4().hex[:8]}",
        tenant_id=namespace,
        source_type=ChunkSourceType.OEM_MANUAL_SECTION,
        text="Inspect intake airflow path and clear any obstruction.",
        machine_model="x200",
        manual_version="v3",
        source_ref=SourceRef(doc_id="manual_x200_v3", page=184),
        content_confidence=0.95,
    )
    vector_store.upsert(
        "oem_manuals",
        namespace,
        [chunk],
        embedder.embed_texts([chunk.text]),
    )
    results = vector_store.query(
        "oem_manuals",
        namespace,
        embedder.embed_query("check airflow obstruction"),
        filter={"machine_model": "x200", "manual_version": "v3"},
        top_k=3,
        sparse_terms=["airflow", "obstruction"],
    )
    assert results
    assert results[0].chunk.chunk_id == chunk.chunk_id
