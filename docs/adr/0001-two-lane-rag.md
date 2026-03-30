# ADR 0001: Two-Lane RAG Maintenance Copilot

## Status

Accepted

## Context

The system must answer troubleshooting questions using two evidence lanes:

- OEM manuals: stable, structured, versioned, and authoritative for procedure and safety.
- Historical technician logs: noisy, append-heavy, semi-structured, and useful as contextual precedent.

The system also needs:

- hard tenant isolation
- citation-first outputs
- resumable troubleshooting sessions
- cost controls on embeddings and visual processing

## Decision

Build a Python service with:

- FastAPI for service exposure
- deterministic orchestration, not a freeform agent loop
- text-first embeddings across both lanes
- optional multimodal side retrieval for manual pages that remain meaningfully visual after text extraction
- namespace-per-tenant vector isolation
- rules-first log normalization with optional small-LLM fallback

## Consequences

Positive:

- lower hallucination risk
- stronger auditability
- simpler tenant isolation story
- lower primary vector storage footprint
- easier replay and shift handoff through persisted session state

Negative:

- multimodal recall is only as good as the targeted side index coverage
- log normalization quality depends on evidence anchoring and confidence calibration
- Pinecone-centric operational defaults trade some backend portability for speed of deployment
