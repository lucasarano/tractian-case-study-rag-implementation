from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from maintenance_copilot.domain import (
    AnswerEnvelope,
    AnswerRequest,
    AssetMetadata,
    CheckRecord,
    CopilotAnswer,
    CreateSessionRequest,
    Hypothesis,
    RecommendedCheck,
    RetrievedChunk,
    SessionRecord,
    SessionState,
    SupportingEvidence,
    SuspectedCause,
    VerifiedIdentity,
)
from maintenance_copilot.providers import AnswerGenerator
from maintenance_copilot.retrieval import RetrievalService
from maintenance_copilot.sessions import AssetCatalog, ConversationCache, SessionRepository


class WorkOrderNoteWriter(Protocol):
    def write(
        self,
        work_order_id: str,
        note: str,
        *,
        tenant_id: str,
        session_id: str | None,
    ) -> None:
        ...


class EscalationSink(Protocol):
    def escalate(self, session_id: str, reason: str) -> None:
        ...


class NoopWorkOrderNoteWriter:
    def write(
        self,
        work_order_id: str,
        note: str,
        *,
        tenant_id: str,
        session_id: str | None,
    ) -> None:
        return None


class NoopEscalationSink:
    def escalate(self, session_id: str, reason: str) -> None:
        return None


class CitationFirstAnswerComposer:
    def compose(
        self,
        *,
        user_text: str,
        asset: AssetMetadata,
        state: SessionState,
        evidence: list[RetrievedChunk],
    ) -> CopilotAnswer:
        supporting: list[SupportingEvidence] = []
        chunk_to_citation: dict[str, str] = {}
        manual_evidence = [item for item in evidence if item.chunk.is_manual]
        log_evidence = [item for item in evidence if not item.chunk.is_manual]

        for index, item in enumerate(evidence, start=1):
            prefix = "M" if item.chunk.is_manual else "L"
            citation_id = f"{prefix}{index}"
            chunk_to_citation[item.chunk.chunk_id] = citation_id
            supporting.append(
                SupportingEvidence(
                    citation_id=citation_id,
                    source_type=item.chunk.source_family,
                    citation=item.chunk.citation(),
                    excerpt=item.chunk.excerpt(),
                )
            )

        issue_summary = state.issue_summary or user_text
        if not manual_evidence:
            return CopilotAnswer(
                issue_summary=issue_summary,
                suspected_causes=self._suspected_causes(evidence),
                recommended_checks=[],
                required_tools=[],
                safety_warnings=[
                    "No strong OEM-backed procedure was retrieved, "
                    "so the copilot is withholding procedural steps."
                ],
                supporting_evidence=supporting,
                confidence=0.2,
                urgency=self._urgency(user_text, asset),
                escalate_if=[
                    "No OEM-cited procedure matches the symptom strongly enough.",
                    "The asset condition worsens while waiting for supervisor review.",
                ],
                follow_up_question=(
                    "Can you confirm the exact fault code, subsystem, "
                    "or the latest measured temperature?"
                ),
            )

        checks = [
            RecommendedCheck(
                step=self._extract_step(item.chunk.text),
                expected=self._expected_result(item.chunk.text),
                stop_if=self._stop_condition(item.chunk.text),
                citations=[chunk_to_citation[item.chunk.chunk_id]],
            )
            for item in manual_evidence[:3]
        ]
        safety_warnings = self._safety_warnings(manual_evidence, asset)
        required_tools = self._required_tools(manual_evidence, log_evidence)
        confidence = self._confidence(manual_evidence, log_evidence)
        return CopilotAnswer(
            issue_summary=issue_summary,
            suspected_causes=self._suspected_causes(evidence),
            recommended_checks=checks,
            required_tools=required_tools,
            safety_warnings=safety_warnings,
            supporting_evidence=supporting,
            confidence=confidence,
            urgency=self._urgency(user_text, asset),
            escalate_if=[
                "OEM-backed checks fail to restore normal operation.",
                "Temperature, vibration, or pressure remains outside "
                "safe range after the first pass.",
            ],
            follow_up_question=self._follow_up_question(user_text, state, log_evidence),
        )

    def _suspected_causes(self, evidence: list[RetrievedChunk]) -> list[SuspectedCause]:
        causes: list[SuspectedCause] = []
        seen: set[str] = set()
        for item in evidence[:3]:
            cause = self._infer_cause(item.chunk.text, item.chunk.issue_type)
            if cause in seen:
                continue
            seen.add(cause)
            why = item.chunk.excerpt(120)
            confidence = round(min(max(item.blended_score, 0.25), 0.95), 2)
            causes.append(SuspectedCause(cause=cause, why=why, confidence=confidence))
        return causes or [
            SuspectedCause(
                cause="insufficient_evidence",
                why="The retrieved evidence is too weak to isolate a cause yet.",
                confidence=0.2,
            )
        ]

    def _extract_step(self, text: str) -> str:
        lowered = text.lower()
        if "inspect" in lowered:
            return self._sentence_with(text, "inspect")
        if "verify" in lowered:
            return self._sentence_with(text, "verify")
        if "check" in lowered:
            return self._sentence_with(text, "check")
        return text.split(".")[0].strip()

    def _expected_result(self, text: str) -> str:
        lowered = text.lower()
        if "unobstructed" in lowered or "clear obstruction" in lowered:
            return "Airflow or access path should be clear and the symptom should stop worsening."
        if "stable" in lowered:
            return "Readings should return to a stable operating range."
        return "This step should confirm or eliminate the cited condition."

    def _stop_condition(self, text: str) -> str:
        lowered = text.lower()
        if any(
            token in lowered
            for token in ["shut down", "lockout", "de-energize", "stop operation"]
        ):
            return "Stop immediately if the OEM procedure calls for shutdown or lockout."
        return "Stop and escalate if the condition worsens during the check."

    def _safety_warnings(
        self,
        manual_evidence: list[RetrievedChunk],
        asset: AssetMetadata,
    ) -> list[str]:
        warnings = []
        for item in manual_evidence:
            lowered = item.chunk.text.lower()
            if any(token in lowered for token in ["warning", "caution", "shut down", "lockout"]):
                warnings.append(item.chunk.excerpt(140))
        if asset.criticality == "high":
            warnings.append(
                "High-criticality asset: do not continue operating "
                "if the symptom escalates during inspection."
            )
        return list(dict.fromkeys(warnings))

    def _required_tools(
        self,
        manual_evidence: list[RetrievedChunk],
        log_evidence: list[RetrievedChunk],
    ) -> list[str]:
        text = " ".join(item.chunk.text.lower() for item in [*manual_evidence, *log_evidence])
        tools = []
        if "filter" in text:
            tools.append("replacement filter or cleaning kit")
        if "temperature" in text or "overheating" in text:
            tools.append("temperature probe")
        if "fan" in text or "motor" in text:
            tools.append("multimeter")
        return tools

    def _confidence(
        self,
        manual_evidence: list[RetrievedChunk],
        log_evidence: list[RetrievedChunk],
    ) -> float:
        if not manual_evidence:
            return 0.2
        scores = [item.blended_score for item in [*manual_evidence[:3], *log_evidence[:2]]]
        bounded = [min(max(score, 0.1), 1.0) for score in scores]
        return round(sum(bounded) / len(bounded), 2)

    def _urgency(self, user_text: str, asset: AssetMetadata) -> str:
        lowered = user_text.lower()
        if asset.criticality == "high":
            return "high"
        if any(token in lowered for token in ["overheat", "shutdown", "trip", "smoke", "burning"]):
            return "high"
        if any(token in lowered for token in ["vibration", "pressure", "leak"]):
            return "medium"
        return "low"

    def _follow_up_question(
        self,
        user_text: str,
        state: SessionState,
        log_evidence: list[RetrievedChunk],
    ) -> str | None:
        lowered = user_text.lower()
        if "overheat" in lowered and "temp_c" not in state.measurements:
            return "What temperature are you seeing and after how many minutes of runtime?"
        if log_evidence:
            return "When was the last service or filter change recorded on this machine?"
        return None

    def _infer_cause(self, text: str, issue_type: list[str]) -> str:
        lowered = text.lower()
        if "filter" in lowered:
            return "restricted_filter"
        if "airflow" in lowered or "blocked" in lowered:
            return "restricted_airflow"
        if "fan" in lowered:
            return "fan_issue"
        if issue_type:
            return issue_type[0]
        return lowered.split(".")[0][:64]

    def _sentence_with(self, text: str, token: str) -> str:
        for sentence in text.split("."):
            if token in sentence.lower():
                return sentence.strip()
        return text.split(".")[0].strip()


class _CopilotGraphState(TypedDict, total=False):
    session_id: str
    identity: dict[str, Any]
    request: dict[str, Any]
    session: dict[str, Any]
    asset: dict[str, Any]
    rewritten_query: str
    evidence: list[dict[str, Any]]
    answer: dict[str, Any]
    needs_clarification: bool
    clarification_prompt: str
    escalate_now: bool


class DeterministicCopilot:
    def __init__(
        self,
        session_repo: SessionRepository,
        asset_catalog: AssetCatalog,
        cache: ConversationCache,
        retrieval: RetrievalService,
        composer: CitationFirstAnswerComposer,
        *,
        answer_generator: AnswerGenerator | None = None,
        work_order_writer: WorkOrderNoteWriter | None = None,
        escalation_sink: EscalationSink | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self.session_repo = session_repo
        self.asset_catalog = asset_catalog
        self.cache = cache
        self.retrieval = retrieval
        self.composer = composer
        self.answer_generator = answer_generator
        self.work_order_writer = work_order_writer or NoopWorkOrderNoteWriter()
        self.escalation_sink = escalation_sink or NoopEscalationSink()
        self.graph = self._build_graph(checkpointer)

    def create_session(
        self,
        identity: VerifiedIdentity,
        request: CreateSessionRequest,
    ) -> SessionRecord:
        asset = AssetMetadata(
            tenant_id=identity.tenant_id,
            site_id=request.site_id,
            machine_id=request.machine_id,
            machine_model=request.machine_model,
            machine_family=request.machine_family,
            criticality=request.criticality,
            aliases=request.aliases,
        )
        self.asset_catalog.upsert(asset)
        return self.session_repo.create(
            tenant_id=identity.tenant_id,
            user_id=identity.subject,
            machine_id=request.machine_id,
            work_order_id=request.work_order_id,
        )

    def answer(self, identity: VerifiedIdentity, request: AnswerRequest) -> AnswerEnvelope:
        session_id = request.session_id or f"s_{uuid4().hex[:12]}"
        result = self.graph.invoke(
            {
                "session_id": session_id,
                "identity": identity.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
            },
            config={"configurable": {"thread_id": session_id}},
        )
        answer = CopilotAnswer.model_validate(result["answer"])
        return AnswerEnvelope(
            session_id=session_id,
            tenant_id=identity.tenant_id,
            answer=answer,
        )

    def _build_graph(self, checkpointer: Any | None):
        graph = StateGraph(_CopilotGraphState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("ask_followup", self._ask_followup)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("compose", self._compose)
        graph.add_node("persist", self._persist)
        graph.add_edge(START, "load_context")
        graph.add_conditional_edges(
            "load_context",
            self._route_after_load,
            {
                "ask_followup": "ask_followup",
                "retrieve": "retrieve",
            },
        )
        graph.add_edge("ask_followup", "persist")
        graph.add_edge("retrieve", "compose")
        graph.add_edge("compose", "persist")
        graph.add_edge("persist", END)
        return graph.compile(checkpointer=checkpointer, name="maintenance-copilot")

    def _load_context(self, state: _CopilotGraphState) -> _CopilotGraphState:
        identity = VerifiedIdentity.model_validate(state["identity"])
        request = AnswerRequest.model_validate(state["request"])
        session = self._load_session(identity, request, state["session_id"])
        asset, clarification_prompt = self._resolve_asset(identity, request)

        session.state.issue_summary = request.message
        session.state.measurements.update(request.measurements)
        if request.work_order_id and not session.work_order_id:
            session.work_order_id = request.work_order_id
        existing_checks = {item.check for item in session.state.checks_completed}
        for check in request.completed_checks:
            if check not in existing_checks:
                session.state.checks_completed.append(CheckRecord(check=check, status="completed"))
        session.updated_at = datetime.now(UTC)

        update: _CopilotGraphState = {
            "session": session.model_dump(mode="json"),
            "needs_clarification": clarification_prompt is not None,
        }
        if asset is not None:
            update["asset"] = asset.model_dump(mode="json")
        if clarification_prompt:
            update["clarification_prompt"] = clarification_prompt
        return update

    def _route_after_load(self, state: _CopilotGraphState) -> str:
        if state.get("needs_clarification"):
            return "ask_followup"
        return "retrieve"

    def _ask_followup(self, state: _CopilotGraphState) -> _CopilotGraphState:
        request = AnswerRequest.model_validate(state["request"])
        session = SessionRecord.model_validate(state["session"])
        urgency = self._fallback_urgency(request.message, request.criticality)
        answer = CopilotAnswer(
            issue_summary=session.state.issue_summary or request.message,
            suspected_causes=[],
            recommended_checks=[],
            required_tools=[],
            safety_warnings=[
                "Additional asset context is required before OEM-backed troubleshooting can begin."
            ],
            supporting_evidence=[],
            confidence=0.1,
            urgency=urgency,
            escalate_if=[
                "The machine condition worsens before the missing asset details are provided.",
            ],
            follow_up_question=state["clarification_prompt"],
        )
        return {"answer": answer.model_dump(mode="json"), "escalate_now": urgency == "high"}

    def _retrieve(self, state: _CopilotGraphState) -> _CopilotGraphState:
        identity = VerifiedIdentity.model_validate(state["identity"])
        request = AnswerRequest.model_validate(state["request"])
        asset = AssetMetadata.model_validate(state["asset"])
        rewritten_query, evidence = self.retrieval.retrieve(
            tenant_id=identity.tenant_id,
            asset=asset,
            user_text=request.message,
            safety_critical=asset.criticality == "high",
        )
        return {
            "rewritten_query": rewritten_query,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        }

    def _compose(self, state: _CopilotGraphState) -> _CopilotGraphState:
        request = AnswerRequest.model_validate(state["request"])
        session = SessionRecord.model_validate(state["session"])
        asset = AssetMetadata.model_validate(state["asset"])
        evidence = [RetrievedChunk.model_validate(item) for item in state.get("evidence", [])]
        if self.answer_generator is not None:
            answer = self.answer_generator.generate(
                user_text=request.message,
                asset=asset,
                state=session.state,
                evidence=evidence,
                safety_critical=asset.criticality == "high",
            )
        else:
            answer = self.composer.compose(
                user_text=request.message,
                asset=asset,
                state=session.state,
                evidence=evidence,
            )
        return {
            "answer": answer.model_dump(mode="json"),
            "escalate_now": answer.urgency == "high"
            and answer.confidence < 0.7,
        }

    def _persist(self, state: _CopilotGraphState) -> _CopilotGraphState:
        request = AnswerRequest.model_validate(state["request"])
        session = SessionRecord.model_validate(state["session"])
        answer = CopilotAnswer.model_validate(state["answer"])
        evidence = [RetrievedChunk.model_validate(item) for item in state.get("evidence", [])]

        session.state.next_actions = [check.step for check in answer.recommended_checks]
        session.state.hypotheses = [
            Hypothesis(cause=cause.cause, confidence=cause.confidence)
            for cause in answer.suspected_causes
        ]
        if state.get("rewritten_query"):
            session.last_context_summary = state["rewritten_query"]
            self.cache.set_summary(session.session_id, state["rewritten_query"])
        session.updated_at = datetime.now(UTC)
        self.session_repo.save(session)

        if evidence:
            self.cache.set_evidence_ids(
                session.session_id,
                [item.chunk.chunk_id for item in evidence],
            )

        work_order_id = session.work_order_id or request.work_order_id
        if work_order_id:
            self.work_order_writer.write(
                work_order_id,
                self._render_work_order_note(answer),
                tenant_id=session.tenant_id,
                session_id=session.session_id,
            )
        if state.get("escalate_now"):
            self.escalation_sink.escalate(
                session.session_id,
                "high-urgency case with limited confidence",
            )
        return {
            "session": session.model_dump(mode="json"),
            "answer": answer.model_dump(mode="json"),
        }

    def _load_session(
        self,
        identity: VerifiedIdentity,
        request: AnswerRequest,
        session_id: str,
    ) -> SessionRecord:
        if request.session_id:
            record = self.session_repo.get(request.session_id)
            if record is None:
                raise ValueError(f"unknown session_id: {request.session_id}")
            if record.tenant_id != identity.tenant_id:
                raise ValueError("session tenant mismatch")
            return record
        return self.session_repo.create(
            tenant_id=identity.tenant_id,
            user_id=identity.subject,
            machine_id=request.machine_id,
            session_id=session_id,
            work_order_id=request.work_order_id,
        )

    def _resolve_asset(
        self,
        identity: VerifiedIdentity,
        request: AnswerRequest,
    ) -> tuple[AssetMetadata | None, str | None]:
        asset = self.asset_catalog.get(identity.tenant_id, request.machine_id)
        if asset:
            return asset, None
        if not request.site_id or not request.machine_model:
            return None, (
                "I need the site_id and machine_model for this machine before I can "
                "retrieve the correct OEM manual and tenant-scoped history."
            )
        asset = AssetMetadata(
            tenant_id=identity.tenant_id,
            site_id=request.site_id,
            machine_id=request.machine_id,
            machine_model=request.machine_model,
            machine_family=request.machine_family,
            criticality=request.criticality,
        )
        self.asset_catalog.upsert(asset)
        return asset, None

    def _render_work_order_note(self, answer: CopilotAnswer) -> str:
        lines = [f"Issue: {answer.issue_summary}", "Checks:"]
        for check in answer.recommended_checks:
            lines.append(f"- {check.step} ({', '.join(check.citations)})")
        lines.append("Evidence:")
        for evidence in answer.supporting_evidence:
            lines.append(f"- {evidence.citation_id}: {evidence.citation}")
        return "\n".join(lines)

    def _fallback_urgency(
        self,
        user_text: str,
        criticality: str,
    ) -> str:
        lowered = user_text.lower()
        if criticality == "high":
            return "high"
        if any(token in lowered for token in ["overheat", "shutdown", "trip", "smoke", "burning"]):
            return "high"
        if any(token in lowered for token in ["vibration", "pressure", "leak"]):
            return "medium"
        return "low"
