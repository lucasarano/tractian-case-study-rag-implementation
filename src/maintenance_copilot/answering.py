from __future__ import annotations

import re
from collections.abc import Sequence

from maintenance_copilot.domain import RecommendedCheck, RetrievedChunk

_INFORMATIONAL_PREFIXES = (
    "what is ",
    "what are ",
    "what does ",
    "what do ",
    "define ",
    "explain ",
    "describe ",
    "tell me about ",
    "summary of ",
    "summarize ",
)

_PROCEDURAL_PREFIXES = (
    "how can i ",
    "how do i ",
    "how to ",
    "steps to ",
    "steps for ",
    "procedure for ",
    "what is the procedure for ",
    "show me how to ",
    "walk me through ",
)

_CHECK_REQUEST_PATTERNS = (
    "what should i check",
    "what do i check",
    "what should i inspect",
    "what can i check",
    "check first",
    "where should i start",
)

_SUBJECT_PATTERNS = (
    re.compile(r"^\s*(?:what is|what are)\s+(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:what does|what do)\s+(.+?)\s+mean\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:define|explain|describe|summarize|summary of|tell me about)\s+(.+?)\s*\??\s*$", re.IGNORECASE),
)

_PROCEDURAL_PATTERNS = (
    re.compile(r"^\s*(?:how can i|how do i|how to|show me how to|walk me through)\s+(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:steps to|steps for|procedure for|what is the procedure for)\s+(.+?)\s*\??\s*$", re.IGNORECASE),
)

_META_PATTERNS = (
    "user is requesting",
    "the user is requesting",
    "user is asking",
    "the user is asking",
    "the user wants",
    "the loaded manual evidence",
    "the retrieved manual evidence",
    "the retrieved evidence",
    "this question asks",
    "the query asks",
    "the query is asking",
)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "do",
    "does",
    "explain",
    "for",
    "how",
    "i",
    "in",
    "is",
    "me",
    "of",
    "on",
    "please",
    "summarize",
    "summary",
    "tell",
    "the",
    "to",
    "what",
}


def is_informational_query(user_text: str) -> bool:
    normalized = " ".join(user_text.lower().split())
    return normalized.startswith(_INFORMATIONAL_PREFIXES)


def is_procedural_query(user_text: str) -> bool:
    normalized = " ".join(user_text.lower().split())
    return normalized.startswith(_PROCEDURAL_PREFIXES)


def is_manual_guidance_query(user_text: str) -> bool:
    return is_informational_query(user_text) or is_procedural_query(user_text)


def is_check_request(user_text: str) -> bool:
    normalized = " ".join(user_text.lower().split())
    return any(pattern in normalized for pattern in _CHECK_REQUEST_PATTERNS)


def extract_question_subject(user_text: str) -> str | None:
    stripped = user_text.strip().rstrip("?")
    for pattern in _SUBJECT_PATTERNS:
        match = pattern.match(stripped)
        if match:
            subject = match.group(1).strip()
            return re.sub(r"\s+", " ", subject).strip(" .")
    return None


def extract_procedure_subject(user_text: str) -> str | None:
    stripped = user_text.strip().rstrip("?")
    for pattern in _PROCEDURAL_PATTERNS:
        match = pattern.match(stripped)
        if match:
            subject = match.group(1).strip()
            return re.sub(r"\s+", " ", subject).strip(" .")
    return None


def select_answer_evidence(
    user_text: str,
    evidence: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    if not is_manual_guidance_query(user_text):
        return list(evidence)
    return [item for item in evidence if item.chunk.is_manual]


def build_direct_information_answer(
    *,
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
    candidate_answer: str | None = None,
) -> str:
    if not manual_evidence_supports_query(user_text, manual_evidence):
        return _missing_information_answer(user_text, manual_evidence)
    if candidate_answer and not looks_like_meta_answer(candidate_answer, user_text):
        if _response_supports_query(candidate_answer, user_text):
            return candidate_answer.strip()
    snippet = _best_manual_snippet(user_text, manual_evidence)
    if snippet and not looks_like_meta_answer(snippet, user_text):
        if _response_supports_query(snippet, user_text):
            return snippet
    return _missing_information_answer(user_text, manual_evidence)


def _response_supports_query(answer: str, user_text: str) -> bool:
    haystack = answer.lower()
    keywords = _query_keywords(user_text)
    if not keywords:
        return bool(answer.strip())
    identifier_keywords = [token for token in keywords if any(ch.isdigit() for ch in token)]
    if identifier_keywords and not all(token in haystack for token in identifier_keywords):
        return False
    matched = [token for token in keywords if token in haystack]
    required_matches = 1 if len(keywords) <= 2 else 2
    return len(matched) >= required_matches


def build_information_follow_up(
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
) -> str | None:
    subject = extract_question_subject(user_text)
    if not subject:
        return None
    if manual_evidence_supports_query(user_text, manual_evidence):
        return f"Do you want the cited manual section for {subject}?"
    return f"Do you want me to search beyond the loaded pages for {subject}?"


def build_direct_procedure_answer(
    *,
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
    checks: Sequence[RecommendedCheck],
) -> str:
    if checks:
        secure_steps = [check.step for check in checks if _is_secure_step(check.step)]
        release_steps = [check.step for check in checks if _is_release_step(check.step)]
        secure_summary = _summarize_step_group(secure_steps[:3])
        release_summary = _summarize_step_group(release_steps[:4])
        if secure_summary and release_summary:
            return (
                f"Follow the OEM procedure: {secure_summary}. "
                f"To release the engine, {release_summary}."
            )
        if secure_summary:
            return f"Follow the OEM procedure: {secure_summary}."
    return _missing_procedure_answer(user_text, manual_evidence)


def build_manual_procedure_checks(
    *,
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
    citations_by_chunk_id: dict[str, str],
) -> list[RecommendedCheck]:
    checks: list[RecommendedCheck] = []
    seen: set[str] = set()
    keywords = _query_keywords(user_text)
    ranked = sorted(
        manual_evidence,
        key=lambda item: _support_score(item, keywords),
        reverse=True,
    )
    top_overlap = _support_score(ranked[0], keywords)[1] if ranked else 0
    anchor_page = (ranked[0].chunk.page or ranked[0].chunk.source_ref.page) if ranked else None
    for item in ranked:
        _, overlap, _ = _support_score(item, keywords)
        page = item.chunk.page or item.chunk.source_ref.page
        on_anchor_pages = anchor_page is not None and page in {anchor_page, anchor_page + 1}
        if not on_anchor_pages and overlap < max(1, top_overlap - 1):
            continue
        text = _normalize_procedure_step(item.chunk.text)
        if not text or text in seen:
            continue
        if not _looks_like_procedure_step(text):
            continue
        citation = citations_by_chunk_id.get(item.chunk.chunk_id)
        if not citation:
            continue
        checks.append(
            RecommendedCheck(
                step=text,
                expected=_procedure_expected(text),
                stop_if=_procedure_stop_if(text),
                citations=[citation],
            )
        )
        seen.add(text)
        if len(checks) >= 8:
            break
    return checks


def filter_procedure_evidence(
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    if not manual_evidence:
        return []
    keywords = _query_keywords(user_text)
    ranked = sorted(
        manual_evidence,
        key=lambda item: _support_score(item, keywords),
        reverse=True,
    )
    top_overlap = _support_score(ranked[0], keywords)[1] if ranked else 0
    anchor_page = (ranked[0].chunk.page or ranked[0].chunk.source_ref.page) if ranked else None
    filtered: list[RetrievedChunk] = []
    for item in ranked:
        _, overlap, _ = _support_score(item, keywords)
        page = item.chunk.page or item.chunk.source_ref.page
        on_anchor_pages = anchor_page is not None and page in {anchor_page, anchor_page + 1}
        if not on_anchor_pages and overlap < max(1, top_overlap - 1):
            continue
        text = " ".join(item.chunk.text.split())
        normalized = _normalize_procedure_step(text) or text
        lowered = text.lower()
        if _looks_like_procedure_step(normalized) or any(
            token in lowered
            for token in [
                "2.9.4 securing the engine against unexpected start-up and releasing it",
                "access to the engine must be secured against unexpected start-up",
                "secure the engine against unexpected start-up:",
                "make the engine operational (release it):",
                "the following activities have been completed:",
            ]
        ):
            filtered.append(item)
    return filtered[:12]


def build_procedure_follow_up(
    user_text: str,
    checks: Sequence[RecommendedCheck],
) -> str | None:
    subject = extract_procedure_subject(user_text)
    if not subject:
        return None
    if checks:
        return f"Do you want the full cited checklist for {subject}?"
    return f"Do you want the cited manual section for {subject}?"


def build_direct_troubleshooting_answer(
    *,
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
    checks: Sequence[RecommendedCheck],
) -> str | None:
    if not checks:
        return None
    causes = _troubleshooting_causes(manual_evidence, user_text)
    step_summary = _summarize_step_group([check.step for check in checks[:3]])
    if causes:
        return (
            f"The OEM troubleshooting table points first to {_join_phrases(causes[:3])}. "
            f"Start with: {step_summary}."
        )
    return f"Start with the OEM troubleshooting checks: {step_summary}."


def build_manual_troubleshooting_checks(
    *,
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
    citations_by_chunk_id: dict[str, str],
) -> list[RecommendedCheck]:
    candidates: list[tuple[int, tuple[int, int, float], RecommendedCheck]] = []
    seen: set[str] = set()
    keywords = _troubleshooting_keywords(user_text)
    ranked = sorted(
        manual_evidence,
        key=lambda item: _support_score(item, keywords),
        reverse=True,
    )
    for item in ranked:
        row = _extract_troubleshooting_row(item)
        if not row:
            continue
        row_support = _troubleshooting_row_support(row, keywords)
        if row_support[1] < min(2, len(keywords)):
            continue
        step = _normalize_troubleshooting_step(row.get("remedy", ""))
        if not step or step in seen:
            continue
        citation = citations_by_chunk_id.get(item.chunk.chunk_id)
        if not citation:
            continue
        cause = row.get("cause", "")
        malfunction = row.get("malfunction", "")
        if _looks_like_action_text(cause) and step.lower().startswith("contact "):
            continue
        candidates.append(
            (
                _troubleshooting_check_priority(step, cause),
                row_support,
                RecommendedCheck(
                    step=step,
                    expected=_troubleshooting_expected(cause, malfunction),
                    stop_if=_troubleshooting_stop_if(step),
                    citations=[citation],
                ),
            )
        )
        seen.add(step)
    candidates.sort(key=lambda item: (item[0], *item[1]), reverse=True)
    return [check for _, _, check in candidates[:5]]


def build_troubleshooting_follow_up(
    user_text: str,
    checks: Sequence[RecommendedCheck],
) -> str | None:
    if not checks:
        return None
    subject = extract_query_subject(user_text)
    if subject:
        return f"Do you want the cited manual rows for {subject}?"
    return "Do you want the cited manual rows for these checks?"


def extract_manual_safety_warnings(manual_evidence: Sequence[RetrievedChunk]) -> list[str]:
    warnings: list[str] = []
    for item in manual_evidence:
        lowered = item.chunk.text.lower()
        if any(
            token in lowered
            for token in [
                "warning",
                "caution",
                "danger zones",
                "must be secured",
                "switched back on",
                "heat-resistant",
                "hot components",
            ]
        ):
            excerpt = item.chunk.excerpt(180)
            if excerpt not in warnings:
                warnings.append(excerpt)
    return warnings[:4]


def looks_like_meta_answer(answer: str, user_text: str) -> bool:
    normalized_answer = " ".join(answer.lower().split()).strip(" .")
    normalized_user = " ".join(user_text.lower().split()).strip(" .?")
    if not normalized_answer:
        return True
    if normalized_answer == normalized_user:
        return True
    if normalized_answer.endswith(":"):
        return True
    subject = extract_query_subject(user_text)
    if subject:
        normalized_subject = " ".join(subject.lower().split()).strip(" .")
        if normalized_answer in {
            normalized_subject,
            f"for {normalized_subject}",
            f"for the {normalized_subject}",
        }:
            return True
    return any(normalized_answer.startswith(pattern) for pattern in _META_PATTERNS)


def manual_evidence_supports_query(
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
) -> bool:
    if not manual_evidence:
        return False

    haystack = " ".join(
        " ".join(
            [
                " ".join(item.chunk.section_path),
                item.chunk.text,
            ]
        ).lower()
        for item in manual_evidence[:4]
    )
    keywords = _query_keywords(user_text)
    if not keywords:
        return True

    identifier_keywords = [token for token in keywords if any(ch.isdigit() for ch in token)]
    if identifier_keywords and not all(token in haystack for token in identifier_keywords):
        return False

    matched = [token for token in keywords if token in haystack]
    required_matches = 1 if len(keywords) <= 2 else 2
    return len(matched) >= required_matches


def _query_keywords(user_text: str) -> list[str]:
    subject = extract_query_subject(user_text) or user_text
    tokens = re.findall(r"[a-z0-9]+", subject.lower())
    keywords: list[str] = []
    for token in tokens:
        if token in _STOPWORDS:
            continue
        if len(token) < 3 and not any(ch.isdigit() for ch in token):
            continue
        if token not in keywords:
            keywords.append(token)
    return keywords


def _missing_information_answer(
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
) -> str:
    subject = extract_question_subject(user_text)
    refs = _manual_refs(manual_evidence)
    suffix = f" The closest retrieved manual pages were {refs}." if refs else ""
    if subject:
        return f"I can't find a direct definition or procedure for {subject} in the loaded manual pages.{suffix}"
    return f"I can't find a direct answer to that in the loaded manual pages.{suffix}"


def _missing_procedure_answer(
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
) -> str:
    subject = extract_procedure_subject(user_text)
    refs = _manual_refs(manual_evidence)
    suffix = f" The closest retrieved manual pages were {refs}." if refs else ""
    if subject:
        return f"I can't find a complete OEM procedure for {subject} in the loaded manual pages.{suffix}"
    return f"I can't find a complete OEM procedure for that in the loaded manual pages.{suffix}"


def _best_manual_snippet(
    user_text: str,
    manual_evidence: Sequence[RetrievedChunk],
) -> str | None:
    keywords = _query_keywords(user_text)
    identifier_keywords = [token for token in keywords if any(ch.isdigit() for ch in token)]
    ranked = sorted(
        manual_evidence[:5],
        key=lambda item: _support_score(item, keywords),
        reverse=True,
    )
    for item in ranked:
        item_haystack = " ".join(
            [
                " ".join(item.chunk.section_path),
                item.chunk.text,
            ]
        ).lower()
        if identifier_keywords and not all(token in item_haystack for token in identifier_keywords):
            continue
        text = " ".join(item.chunk.text.split())
        if not text:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            cleaned = sentence.strip(" -")
            if len(cleaned.split()) < 6:
                continue
            if not keywords or any(keyword in cleaned.lower() for keyword in keywords):
                return cleaned
        excerpt = item.chunk.excerpt(260)
        if excerpt:
            return excerpt
    return None


def _support_score(item: RetrievedChunk, keywords: Sequence[str]) -> tuple[int, int, float]:
    haystack = " ".join(
        [
            " ".join(item.chunk.section_path),
            item.chunk.text,
        ]
    ).lower()
    identifier_overlap = sum(
        1
        for token in keywords
        if any(ch.isdigit() for ch in token) and token in haystack
    )
    overlap = sum(1 for token in keywords if token in haystack)
    return (identifier_overlap, overlap, item.blended_score)


def extract_query_subject(user_text: str) -> str | None:
    return extract_question_subject(user_text) or extract_procedure_subject(user_text)


def _normalize_procedure_step(text: str) -> str | None:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return None
    lowered = cleaned.lower().strip(".")
    if lowered.startswith("2."):
        return None
    replacements = {
        "all foreign objects are removed": "Verify all foreign objects are removed.",
        "all protectives devices are installed and are functioning": "Verify all protective devices are installed and functioning.",
        "all protective devices are installed and are functioning": "Verify all protective devices are installed and functioning.",
        "no outsiders are residing in the danger zones": "Verify no outsiders are in the danger zones.",
        "the tags for the fuel supply are removed": "Remove the tags for the fuel supply.",
        "fuel supply is connected": "Reconnect the fuel supply.",
        "the tag for the electrical power supply is removed": "Remove the tag for the electrical power supply.",
        "the electrical power supply is established": "Re-establish the electrical power supply.",
    }
    for prefix, replacement in replacements.items():
        if lowered.startswith(prefix):
            return replacement
    return cleaned if cleaned.endswith(".") else f"{cleaned}."


def _looks_like_procedure_step(text: str) -> bool:
    lowered = text.lower().strip()
    if lowered.endswith(":"):
        return False
    if lowered.startswith("procedure"):
        return False
    if lowered.startswith("secure the engine against unexpected start-up"):
        return False
    if lowered.startswith("securing the engine against unexpected"):
        return False
    if lowered.startswith("make the engine operational"):
        return False
    if lowered.startswith("access to the engine must be secured"):
        return False
    if lowered.startswith("the following activities have been completed"):
        return False
    if "warning sign" in lowered or "optional" in lowered:
        return False
    action_verbs = (
        "disconnect",
        "mark",
        "remove",
        "reconnect",
        "re-establish",
        "secure",
        "switch",
        "verify",
        "install",
        "wear",
        "let",
        "clear",
        "move",
    )
    return lowered.startswith(action_verbs)


def _procedure_expected(text: str) -> str:
    lowered = text.lower()
    if _is_secure_step(text):
        return "The engine is isolated so it cannot start unexpectedly."
    if _is_release_step(text):
        return "The engine is restored safely for normal operation."
    if "danger zones" in lowered:
        return "The danger zones should be clear before the engine is released."
    return "The cited OEM procedure step should be completed safely."


def _procedure_stop_if(text: str) -> str:
    lowered = text.lower()
    if _is_secure_step(text):
        return "Stop if fuel or electrical isolation cannot be secured or tagged."
    if _is_release_step(text) or "danger zones" in lowered:
        return "Stop if any protective device is missing or anyone remains in the danger zones."
    return "Stop if the OEM safety conditions for this step are not satisfied."


def _is_secure_step(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "disconnect the diesel fuel supply",
            "disconnect the electrical power supply",
            "secure it against being switched back on",
            "mark the cut-off point",
        ]
    )


def _is_release_step(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "verify all foreign objects are removed",
            "verify all protective devices are installed",
            "verify no outsiders are in the danger zones",
            "remove the tags for the fuel supply",
            "reconnect the fuel supply",
            "remove the tag for the electrical power supply",
            "re-establish the electrical power supply",
        ]
    )


def _summarize_step_group(steps: Sequence[str]) -> str:
    cleaned = [step.rstrip(".") for step in steps if step.strip()]
    if not cleaned:
        return ""
    return "; ".join(cleaned)


def _manual_refs(manual_evidence: Sequence[RetrievedChunk]) -> str:
    refs: list[str] = []
    for item in manual_evidence[:3]:
        page = item.chunk.page or item.chunk.source_ref.page
        if page is None:
            continue
        label = f"page {page}"
        if label not in refs:
            refs.append(label)
    if not refs:
        return ""
    if len(refs) == 1:
        return refs[0]
    return ", ".join(refs[:-1]) + f", and {refs[-1]}"


def _troubleshooting_keywords(user_text: str) -> list[str]:
    return [token for token in _query_keywords(user_text) if not token.isdigit()]


def _extract_troubleshooting_row(item: RetrievedChunk) -> dict[str, str] | None:
    if not item.chunk.is_manual:
        return None
    normalized_fields = {
        _normalize_field_name(key): " ".join(value.split())
        for key, value in item.chunk.structured_fields.items()
        if value and value.strip()
    }
    malfunction = (
        normalized_fields.get("malfunction")
        or normalized_fields.get("malfunction_error")
        or normalized_fields.get("symptom")
        or normalized_fields.get("col_1")
        or ""
    )
    cause = normalized_fields.get("cause") or normalized_fields.get("col_2") or ""
    remedy = normalized_fields.get("remedy") or normalized_fields.get("action") or normalized_fields.get("col_3") or ""

    if not cause and not remedy:
        match = re.search(
            r"col_1:\s*(.*?)\s*\|\s*col_2:\s*(.*?)\s*\|\s*col_3:\s*(.*)",
            " ".join(item.chunk.text.split()),
            re.IGNORECASE,
        )
        if match:
            malfunction = malfunction or match.group(1).strip()
            cause = match.group(2).strip()
            remedy = match.group(3).strip()

    if not remedy:
        return None
    return {
        "malfunction": malfunction,
        "cause": cause,
        "remedy": remedy,
    }


def _normalize_field_name(key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    return normalized


def _normalize_troubleshooting_step(remedy: str) -> str | None:
    cleaned = " ".join(remedy.split()).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("visual inspec tion", "visual inspection")
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if sentence.strip()
    ]
    if not sentences:
        return None
    actionable = [
        sentence
        for sentence in sentences
        if not sentence.lower().startswith("contact your nearest")
    ]
    chosen = actionable[0] if actionable else sentences[0]
    chosen = chosen.replace('See "Service Assistance” section.', "").strip()
    chosen = chosen.replace('See "Service Assistance" section.', "").strip()
    chosen = chosen.replace("See “Service” section.", "").strip()
    chosen = chosen.replace("See “Service” section", "").strip()
    chosen = chosen.strip(" .")
    if not chosen:
        return None
    return f"{chosen}."


def _troubleshooting_expected(cause: str, malfunction: str) -> str:
    cause_text = cause.strip().rstrip(".")
    malfunction_text = malfunction.strip().rstrip(".")
    if cause_text:
        return f"This check confirms or rules out: {cause_text}."
    if malfunction_text:
        return f"This check addresses: {malfunction_text}."
    return "The cited OEM troubleshooting check should be completed safely."


def _troubleshooting_stop_if(step: str) -> str:
    lowered = step.lower()
    if "contact your nearest authorized" in lowered or "authorized kohler service" in lowered:
        return "Stop and escalate to authorized service if the OEM step requires it."
    return "Stop if the condition worsens or the OEM step cannot be completed safely."


def _troubleshooting_row_support(
    row: dict[str, str],
    keywords: Sequence[str],
) -> tuple[int, int, float]:
    haystack = " ".join(row.values()).lower()
    identifier_overlap = sum(
        1 for token in keywords if any(ch.isdigit() for ch in token) and token in haystack
    )
    overlap = sum(1 for token in keywords if token in haystack)
    symptom_overlap = sum(
        1 for token in keywords if token not in {"check", "load", "under", "bar"} and token in haystack
    )
    return (identifier_overlap, max(overlap, symptom_overlap), 0.0)


def _troubleshooting_check_priority(step: str, cause: str) -> int:
    lowered_step = step.lower()
    lowered_cause = cause.lower()
    if "oil level" in lowered_cause or lowered_step.startswith("fill "):
        return 5
    if lowered_step.startswith(("carry out ", "inspect ", "drain ", "clean ", "seal ")):
        return 4
    if lowered_step.startswith("check ") and "replace" not in lowered_step:
        return 4
    if "replace" in lowered_step:
        return 3
    if lowered_step.startswith("contact "):
        return 1
    return 2


def _looks_like_action_text(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered.startswith(
        (
            "check ",
            "replace ",
            "drain ",
            "fill ",
            "carry out ",
            "clean ",
            "seal ",
            "adjust ",
            "contact ",
        )
    )


def _troubleshooting_causes(
    manual_evidence: Sequence[RetrievedChunk],
    user_text: str,
) -> list[str]:
    causes: list[str] = []
    keywords = _troubleshooting_keywords(user_text)
    ranked = sorted(
        manual_evidence,
        key=lambda item: _support_score(item, keywords),
        reverse=True,
    )
    for item in ranked:
        row = _extract_troubleshooting_row(item)
        if not row:
            continue
        cause = row.get("cause", "").strip().rstrip(".")
        if cause and cause not in causes:
            causes.append(cause)
        if len(causes) >= 3:
            break
    return causes


def _join_phrases(parts: Sequence[str]) -> str:
    cleaned = [part.strip().rstrip(".") for part in parts if part.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"
