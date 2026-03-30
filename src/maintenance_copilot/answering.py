from __future__ import annotations

import re
from collections.abc import Sequence

from maintenance_copilot.domain import RetrievedChunk

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

_SUBJECT_PATTERNS = (
    re.compile(r"^\s*(?:what is|what are)\s+(.+?)\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:what does|what do)\s+(.+?)\s+mean\s*\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:define|explain|describe|summarize|summary of|tell me about)\s+(.+?)\s*\??\s*$", re.IGNORECASE),
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


def extract_question_subject(user_text: str) -> str | None:
    stripped = user_text.strip().rstrip("?")
    for pattern in _SUBJECT_PATTERNS:
        match = pattern.match(stripped)
        if match:
            subject = match.group(1).strip()
            return re.sub(r"\s+", " ", subject).strip(" .")
    return None


def select_answer_evidence(
    user_text: str,
    evidence: Sequence[RetrievedChunk],
) -> list[RetrievedChunk]:
    if not is_informational_query(user_text):
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


def looks_like_meta_answer(answer: str, user_text: str) -> bool:
    normalized_answer = " ".join(answer.lower().split()).strip(" .")
    normalized_user = " ".join(user_text.lower().split()).strip(" .?")
    if not normalized_answer:
        return True
    if normalized_answer == normalized_user:
        return True
    if normalized_answer.endswith(":"):
        return True
    subject = extract_question_subject(user_text)
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
    subject = extract_question_subject(user_text) or user_text
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
