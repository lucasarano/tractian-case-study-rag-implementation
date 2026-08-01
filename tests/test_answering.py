from maintenance_copilot.answering import (
    build_direct_information_answer,
    build_direct_procedure_answer,
    build_manual_procedure_checks,
    build_manual_troubleshooting_checks,
    build_direct_troubleshooting_answer,
    manual_evidence_supports_query,
)
from maintenance_copilot.domain import (
    AssetMetadata,
    ChunkSourceType,
    KnowledgeChunk,
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
    source_type: ChunkSourceType = ChunkSourceType.OEM_MANUAL_SECTION,
    structured_fields: dict[str, str] | None = None,
) -> RetrievedChunk:
    chunk = KnowledgeChunk(
        chunk_id=f"manual:test:{page}:{abs(hash(text))}",
        tenant_id="companyA",
        source_type=source_type,
        text=text,
        source_ref=SourceRef(doc_id="manual_test", page=page),
        machine_model="KD27V12",
        machine_family="generator",
        manual_version="v1",
        page=page,
        section_path=section_path or ["Maintenance", f"Page {page}"],
        content_confidence=0.95,
        structured_fields=structured_fields or {},
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


def test_procedure_helpers_build_direct_answer_and_checks() -> None:
    evidence = [
        _manual_hit(
            page=31,
            section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
            text="Disconnect the diesel fuel supply.",
            score=0.92,
        ),
        _manual_hit(
            page=31,
            section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
            text="Mark the cut-off point with a tag.",
            score=0.91,
        ),
        _manual_hit(
            page=31,
            section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
            text="Disconnect the electrical power supply and secure it against being switched back on.",
            score=0.9,
        ),
        _manual_hit(
            page=32,
            section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
            text="The tags for the fuel supply are removed.",
            score=0.88,
        ),
        _manual_hit(
            page=32,
            section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
            text="Fuel supply is connected.",
            score=0.87,
        ),
        _manual_hit(
            page=32,
            section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
            text="The electrical power supply is established.",
            score=0.86,
        ),
    ]
    citations = {item.chunk.chunk_id: f"M{index}" for index, item in enumerate(evidence, start=1)}

    checks = build_manual_procedure_checks(
        user_text="how can I secure the engine against unexpected startup and releasing it",
        manual_evidence=evidence,
        citations_by_chunk_id=citations,
    )
    answer = build_direct_procedure_answer(
        user_text="how can I secure the engine against unexpected startup and releasing it",
        manual_evidence=evidence,
        checks=checks,
    )

    assert len(checks) >= 4
    assert any("Disconnect the diesel fuel supply" in check.step for check in checks)
    assert any("Reconnect the fuel supply" in check.step for check in checks)
    assert answer.startswith("Follow the OEM procedure:")


def test_procedure_query_composer_returns_steps_without_suspected_causes() -> None:
    composer = CitationFirstAnswerComposer()

    answer = composer.compose(
        user_text="how can I secure the engine against unexpected startup and releasing it",
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
                page=31,
                section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
                text="Disconnect the diesel fuel supply.",
                score=0.92,
            ),
            _manual_hit(
                page=31,
                section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
                text="Disconnect the electrical power supply and secure it against being switched back on.",
                score=0.91,
            ),
            _manual_hit(
                page=32,
                section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
                text="The tags for the fuel supply are removed.",
                score=0.9,
            ),
            _manual_hit(
                page=32,
                section_path=["Safety", "Securing the engine against unexpected start-up and releasing it"],
                text="Fuel supply is connected.",
                score=0.89,
            ),
        ],
    )

    assert answer.issue_summary.startswith("Follow the OEM procedure:")
    assert answer.suspected_causes == []
    assert len(answer.recommended_checks) >= 3
    assert answer.escalate_if == []


def test_troubleshooting_helpers_build_direct_answer_and_checks() -> None:
    evidence = [
        _manual_hit(
            page=40,
            section_path=["Operating faults", "Errors – Cause – Remedy"],
            source_type=ChunkSourceType.OEM_MANUAL_TABLE_ROW,
            text=(
                "col_1: Engine oil pressure is too low. | "
                "col_2: Oil level in oil pan is too low. | "
                "col_3: Fill oil to prescribed mark."
            ),
            structured_fields={
                "col_1": "Engine oil pressure is too low.",
                "col_2": "Oil level in oil pan is too low.",
                "col_3": "Fill oil to prescribed mark.",
            },
            score=0.93,
        ),
        _manual_hit(
            page=40,
            section_path=["Operating faults", "Errors – Cause – Remedy"],
            source_type=ChunkSourceType.OEM_MANUAL_TABLE_ROW,
            text=(
                "col_1: Engine oil pressure is too low. | "
                "col_2: Lubricating oil is too thin (oil diluted by diesel fuel). | "
                "col_3: Drain the oil and refill with the specified oil."
            ),
            structured_fields={
                "col_1": "Engine oil pressure is too low.",
                "col_2": "Lubricating oil is too thin (oil diluted by diesel fuel).",
                "col_3": "Drain the oil and refill with the specified oil.",
            },
            score=0.92,
        ),
        _manual_hit(
            page=40,
            section_path=["Operating faults", "Errors – Cause – Remedy"],
            source_type=ChunkSourceType.OEM_MANUAL_TABLE_ROW,
            text=(
                "col_1: Engine oil pressure is too low. | "
                "col_2: Pressure sensor has a fault. | "
                "col_3: Check the oil pressure and replace the damaged pressure transducer. "
                "Contact your nearest authorized Kohler service representative."
            ),
            structured_fields={
                "col_1": "Engine oil pressure is too low.",
                "col_2": "Pressure sensor has a fault.",
                "col_3": (
                    "Check the oil pressure and replace the damaged pressure transducer. "
                    "Contact your nearest authorized Kohler service representative."
                ),
            },
            score=0.91,
        ),
    ]
    citations = {item.chunk.chunk_id: f"M{index}" for index, item in enumerate(evidence, start=1)}

    checks = build_manual_troubleshooting_checks(
        user_text="Low oil pressure at 2.0 bar under load — what should I check?",
        manual_evidence=evidence,
        citations_by_chunk_id=citations,
    )
    answer = build_direct_troubleshooting_answer(
        user_text="Low oil pressure at 2.0 bar under load — what should I check?",
        manual_evidence=evidence,
        checks=checks,
    )

    assert len(checks) == 3
    assert checks[0].step == "Fill oil to prescribed mark."
    assert any("Drain the oil and refill with the specified oil." == check.step for check in checks)
    assert any("Check the oil pressure and replace the damaged pressure transducer." == check.step for check in checks)
    assert answer is not None
    assert "OEM troubleshooting table points first to" in answer


def test_troubleshooting_query_composer_returns_direct_manual_checks() -> None:
    composer = CitationFirstAnswerComposer()

    answer = composer.compose(
        user_text="Low oil pressure at 2.0 bar under load — what should I check?",
        asset=AssetMetadata(
            tenant_id="companyA",
            site_id="site-1",
            machine_id="gen-1",
            machine_model="KD27V12",
            machine_family="generator",
            criticality="high",
        ),
        state=SessionState(),
        evidence=[
            _manual_hit(
                page=40,
                section_path=["Operating faults", "Errors – Cause – Remedy"],
                source_type=ChunkSourceType.OEM_MANUAL_TABLE_ROW,
                text=(
                    "col_1: Engine oil pressure is too low. | "
                    "col_2: Oil level in oil pan is too low. | "
                    "col_3: Fill oil to prescribed mark."
                ),
                structured_fields={
                    "col_1": "Engine oil pressure is too low.",
                    "col_2": "Oil level in oil pan is too low.",
                    "col_3": "Fill oil to prescribed mark.",
                },
                score=0.93,
            ),
            _manual_hit(
                page=40,
                section_path=["Operating faults", "Errors – Cause – Remedy"],
                source_type=ChunkSourceType.OEM_MANUAL_TABLE_ROW,
                text=(
                    "col_1: Engine oil pressure is too low. | "
                    "col_2: Pressure sensor has a fault. | "
                    "col_3: Check the oil pressure and replace the damaged pressure transducer."
                ),
                structured_fields={
                    "col_1": "Engine oil pressure is too low.",
                    "col_2": "Pressure sensor has a fault.",
                    "col_3": "Check the oil pressure and replace the damaged pressure transducer.",
                },
                score=0.92,
            ),
        ],
    )

    assert answer.issue_summary.startswith("The OEM troubleshooting table points first to")
    assert answer.suspected_causes == []
    assert len(answer.recommended_checks) == 2
    assert answer.recommended_checks[0].step == "Fill oil to prescribed mark."
    assert answer.urgency == "high"
