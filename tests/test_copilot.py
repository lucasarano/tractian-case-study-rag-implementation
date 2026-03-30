from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from maintenance_copilot.api import create_app
from maintenance_copilot.config import Settings
from maintenance_copilot.domain import (
    AnswerRequest,
    AssetMetadata,
    ChunkSourceType,
    CopilotAnswer,
    IngestLogRequest,
    IngestManualRequest,
    KnowledgeChunk,
    ManualPageSeed,
    RecommendedCheck,
    SourceRef,
    SupportingEvidence,
    VerifiedIdentity,
)
from maintenance_copilot.ingest import LogIngestPipeline, ManualIngestPipeline
from maintenance_copilot.orchestration import CitationFirstAnswerComposer, DeterministicCopilot
from maintenance_copilot.providers import HashTextEmbedder, HeuristicReranker, InMemoryVectorStore
from maintenance_copilot.retrieval import RetrievalService
from maintenance_copilot.sessions import (
    InMemoryAssetCatalog,
    InMemoryConversationCache,
    InMemorySessionRepository,
)


class DummyNormalizer:
    def __init__(self) -> None:
        self.calls = 0

    def normalize(self, markdown: str):
        self.calls += 1
        from maintenance_copilot.domain import NormalizedIncident

        return NormalizedIncident(
            summary_text="LLM-normalized summary",
            component=["cooling_system"],
            issue_type=["overheating"],
            candidate_fields={"raw": markdown[:20]},
            field_confidence={"issue_type": 0.7},
            method="rules_then_small_llm",
        )


def build_copilot() -> tuple[DeterministicCopilot, ManualIngestPipeline, LogIngestPipeline]:
    settings = Settings(runtime_env="test")
    embedder = HashTextEmbedder(dimensions=64)
    vector_store = InMemoryVectorStore()
    manual_ingest = ManualIngestPipeline(embedder, vector_store)
    log_ingest = LogIngestPipeline(embedder, vector_store, confidence_threshold=0.8)
    retrieval = RetrievalService(settings, embedder, vector_store, HeuristicReranker())
    copilot = DeterministicCopilot(
        InMemorySessionRepository(),
        InMemoryAssetCatalog(),
        InMemoryConversationCache(),
        retrieval,
        CitationFirstAnswerComposer(),
    )
    return copilot, manual_ingest, log_ingest


def test_tenant_id_is_derived_from_identity_not_request_body() -> None:
    copilot, manual_ingest, log_ingest = build_copilot()
    identity = VerifiedIdentity(subject="user-1", tenant_id="companyA")
    copilot.asset_catalog.upsert(
        AssetMetadata(
            tenant_id="companyA",
            site_id="site-1",
            machine_id="mx17",
            machine_model="x200",
            machine_family="compressor",
            criticality="medium",
        )
    )
    manual_ingest.ingest(
        IngestManualRequest(
            doc_id="manual_x200_v3",
            manufacturer="OEM",
            machine_model="x200",
            manual_version="v3",
            pages=[
                ManualPageSeed(
                    page=184,
                    text=(
                        "Inspect intake airflow path and clear any obstruction "
                        "before checking electrical load."
                    ),
                )
            ],
            tenant_id="companyB",
        ),
        tenant_id="companyA",
    )
    manual_ingest.ingest(
        IngestManualRequest(
            doc_id="manual_x200_v9",
            manufacturer="OEM",
            machine_model="x200",
            manual_version="v9",
            pages=[
                ManualPageSeed(
                    page=190,
                    text="Company B only: replace the pump manifold immediately.",
                )
            ],
            tenant_id="companyA",
        ),
        tenant_id="companyB",
    )
    log_ingest.ingest(
        IngestLogRequest(
            machine_id="mx17",
            site_id="site-1",
            machine_model="x200",
            machine_family="compressor",
            timestamp=datetime(2026, 1, 12, 9, 14, tzinfo=UTC),
            path="logs/2026/01/12/incident_4421.md",
            markdown=(
                "MX17 overheated after 20 minutes.\n"
                "Found intake filter clogged; cleaned and restarted.\n"
                "Temp stable at 72C."
            ),
        ),
        tenant_id="companyA",
    )
    answer = copilot.answer(
        identity,
        AnswerRequest(
            tenant_id="companyB",
            machine_id="mx17",
            message="MX17 overheating after 20 minutes. What should I check first?",
        ),
    )
    assert answer.tenant_id == "companyA"
    citations = [item.citation for item in answer.answer.supporting_evidence]
    assert any("manual_x200_v3#page=184" in citation for citation in citations)
    assert all("manual_x200_v9" not in citation for citation in citations)


def test_citation_validator_rejects_unknown_evidence_reference() -> None:
    with pytest.raises(ValidationError):
        CopilotAnswer(
            issue_summary="test",
            suspected_causes=[],
            recommended_checks=[
                RecommendedCheck(
                    step="Inspect the intake",
                    expected="Airflow clears",
                    stop_if="Condition worsens",
                    citations=["M99"],
                )
            ],
            required_tools=[],
            safety_warnings=[],
            supporting_evidence=[
                SupportingEvidence(
                    citation_id="M1",
                    source_type="oem_manual",
                    citation="manual#page=10",
                    excerpt="inspect intake",
                )
            ],
            confidence=0.7,
            urgency="medium",
            escalate_if=[],
        )


def test_log_normalizer_only_runs_when_rules_confidence_is_low() -> None:
    embedder = HashTextEmbedder(dimensions=32)
    vector_store = InMemoryVectorStore()
    normalizer = DummyNormalizer()
    pipeline = LogIngestPipeline(
        embedder,
        vector_store,
        normalizer=normalizer,
        confidence_threshold=0.8,
    )
    pipeline.ingest(
        IngestLogRequest(
            machine_id="mx17",
            site_id="site-1",
            machine_model="x200",
            machine_family="compressor",
            path="logs/2026/01/12/incident_1.md",
            markdown=(
                "MX17 overheating.\n"
                "Found intake filter clogged.\n"
                "Cleaned and restarted; stable."
            ),
        ),
        tenant_id="companyA",
    )
    assert normalizer.calls == 0

    pipeline.ingest(
        IngestLogRequest(
            machine_id="mx18",
            site_id="site-1",
            machine_model="x200",
            machine_family="compressor",
            path="logs/2026/01/13/incident_2.md",
            markdown="Bad run.\nSomething odd.\nNeeded help.",
        ),
        tenant_id="companyA",
    )
    assert normalizer.calls == 1


def test_no_procedure_steps_without_oem_evidence() -> None:
    settings = Settings(runtime_env="test")
    embedder = HashTextEmbedder(dimensions=32)
    vector_store = InMemoryVectorStore()
    retrieval = RetrievalService(settings, embedder, vector_store, HeuristicReranker())
    copilot = DeterministicCopilot(
        InMemorySessionRepository(),
        InMemoryAssetCatalog(),
        InMemoryConversationCache(),
        retrieval,
        CitationFirstAnswerComposer(),
    )
    copilot.asset_catalog.upsert(
        AssetMetadata(
            tenant_id="companyA",
            site_id="site-1",
            machine_id="mx17",
            machine_model="x200",
            machine_family="compressor",
            criticality="high",
        )
    )
    log_chunk = KnowledgeChunk(
        chunk_id="log:mx17:1",
        tenant_id="companyA",
        source_type=ChunkSourceType.HISTORICAL_INSIGHT,
        machine_id="mx17",
        machine_model="x200",
        machine_family="compressor",
        site_id="site-1",
        text="MX17 overheated and was stabilized after cleaning the filter.",
        source_ref=SourceRef(path="logs/a.md"),
        content_confidence=0.8,
    )
    vector_store.upsert(
        "historical_insights",
        "companyA",
        [log_chunk],
        embedder.embed_texts([log_chunk.text]),
    )
    answer = copilot.answer(
        VerifiedIdentity(subject="u1", tenant_id="companyA"),
        AnswerRequest(machine_id="mx17", message="Machine overheating during startup"),
    )
    assert answer.answer.recommended_checks == []
    assert "withholding procedural steps" in answer.answer.safety_warnings[0]


def test_readyz_in_test_mode() -> None:
    with TestClient(create_app(Settings(runtime_env="test"))) as client:
        response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"


def test_manual_job_lifecycle_and_answer_api() -> None:
    headers = {"Authorization": "Bearer dev:tech-001@companyA"}
    with TestClient(create_app(Settings(runtime_env="test"))) as client:
        create_job = client.post(
            "/v1/ingest/manuals/jobs",
            headers=headers,
            json={
                "doc_id": "manual_x200_v3",
                "manufacturer": "OEM",
                "machine_model": "x200",
                "machine_family": "compressor",
                "manual_version": "v3",
                "pages": [
                    {
                        "page": 184,
                        "section_path": ["Troubleshooting", "Overheating"],
                        "text": "Inspect intake airflow path and clear any obstruction.",
                    }
                ],
            },
        )
        assert create_job.status_code == 200
        job_id = create_job.json()["job_id"]

        container = client.app.state.container
        job = container.manual_job_repo.claim_next_pending()
        assert job is not None
        container.manual_job_processor.process(job)

        job_response = client.get(f"/v1/ingest/manuals/jobs/{job_id}", headers=headers)
        assert job_response.status_code == 200
        assert job_response.json()["status"] == "succeeded"

        log_response = client.post(
            "/v1/ingest/logs",
            headers=headers,
            json={
                "machine_id": "mx17",
                "site_id": "site-1",
                "machine_model": "x200",
                "machine_family": "compressor",
                "path": "logs/2026/01/12/incident_4421.md",
                "markdown": (
                    "MX17 overheated after 20 minutes.\n"
                    "Found intake filter clogged; cleaned and restarted.\n"
                    "Temp stable at 72C."
                ),
            },
        )
        assert log_response.status_code == 200

        answer_response = client.post(
            "/v1/copilot/answer",
            headers=headers,
            json={
                "machine_id": "mx17",
                "site_id": "site-1",
                "machine_model": "x200",
                "machine_family": "compressor",
                "message": "MX17 overheating after 20 minutes. What should I check first?",
            },
        )
        assert answer_response.status_code == 200
        answer = answer_response.json()["answer"]
        assert answer["recommended_checks"]
        assert any(item["source_type"] == "oem_manual" for item in answer["supporting_evidence"])
        assert any(
            item["source_type"] == "historical_log"
            for item in answer["supporting_evidence"]
        )
