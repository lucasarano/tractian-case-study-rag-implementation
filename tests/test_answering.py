from maintenance_copilot.answering import (
    build_direct_information_answer,
    manual_evidence_supports_query,
)
from maintenance_copilot.domain import (
    AssetMetadata,
    ChunkSourceType,
    RetrievedChunk,
    SessionState,
    SourceRef,
)
from maintenance_copilot.orchestration import CitationFirstAnswerComposer


def _manual_hit(
    *,
    text: str,
    page: int,
    section_path: list[str] | None = None,
    score: float = 0.82,
) -> RetrievedChunk:
    from maintenance_copilot.domain import KnowledgeChunk

    chunk = KnowledgeChunk(
        chunk_id=f"manual:test:{page}",
        tenant_id="companyA",
        source_type=ChunkSourceType.OEM_MANUAL_SECTION,
        text=text,
        source_ref=SourceRef(doc_id="manual_test", page=page),
        machine_model="KD27V12",
        machine_family="generator",
        manual_version="v1",
        page=page,
        section_path=section_path or ["Maintenance", f"Page {page}"],
        content_confidence=0.95,
    )
    return RetrievedChunk(
        chunk=chunk,
        corpus="oem_manuals",
        score=score,
        rerank_score=score,
    )


def test_direct_information_answer_uses_manual_excerpt_when_supported() -> None:
    evidence = [
        _manual_hit(
            page=24,
            section_path=["Maintenance", "SL2"],
            text=(
                "SL2 maintenance is the scheduled major service interval for the generator "
                "engine. It includes a deeper inspection of filters, cooling components, "
                "and other wear items."
            ),
        )
    ]

    assert manual_evidence_supports_query(
        "what is SL2 maintenance of power generation engines",
        evidence,
    )
    answer = build_direct_information_answer(
        user_text="what is SL2 maintenance of power generation engines",
        manual_evidence=evidence,
    )

    assert answer.startswith("SL2 maintenance is the scheduled major service interval")


def test_direct_information_answer_reports_missing_definition_when_manual_is_off_topic() -> None:
    evidence = [
        _manual_hit(
            page=24,
            section_path=["Operations", "General"],
            text=(
                "Power production plant operators operate, monitor and maintain switchboards "
                "and related equipment in electrical control centers."
            ),
        )
    ]

    assert not manual_evidence_supports_query(
        "what is SL2 maintenance of power generation engines",
        evidence,
    )
    answer = build_direct_information_answer(
        user_text="what is SL2 maintenance of power generation engines",
        manual_evidence=evidence,
    )

    assert "can't find a direct definition or procedure" in answer
    assert "page 24" in answer


def test_direct_information_answer_skips_non_identifier_snippets_for_identifier_queries() -> None:
    evidence = [
        _manual_hit(
            page=24,
            section_path=["Operations", "General"],
            score=0.9,
            text=(
                "Power production plant operators operate, monitor and maintain switchboards "
                "and related equipment in electrical control centers."
            ),
        ),
        _manual_hit(
            page=24,
            section_path=["Maintenance", "SL2"],
            score=0.88,
            text="For the SL2 maintenance of power generation engines:",
        ),
    ]

    answer = build_direct_information_answer(
        user_text="what is SL2 maintenance of power generation engines",
        manual_evidence=evidence,
        candidate_answer=(
            "The loaded manual evidence does not provide a definition or explanation for "
            "'SL2 maintenance of power generation engines'."
        ),
    )

    assert answer.startswith("I can't find a direct definition or procedure")


def test_information_query_composer_returns_direct_answer_without_troubleshooting_fill() -> None:
    composer = CitationFirstAnswerComposer()

    answer = composer.compose(
        user_text="what is SL2 maintenance",
        asset=AssetMetadata(
            tenant_id="companyA",
            site_id="site-1",
            machine_id="gen-1",
            machine_model="KD27V12",
            machine_family="generator",
            criticality="medium",
        ),
        state=SessionState(),
        evidence=[
            _manual_hit(
                page=24,
                section_path=["Maintenance", "SL2"],
                text=(
                    "SL2 maintenance is the scheduled major service interval for the generator "
                    "engine. It includes inspection of filters and cooling components."
                ),
            )
        ],
    )

    assert answer.issue_summary.startswith("SL2 maintenance is the scheduled major service interval")
    assert answer.suspected_causes == []
    assert answer.recommended_checks == []
    assert answer.escalate_if == []
