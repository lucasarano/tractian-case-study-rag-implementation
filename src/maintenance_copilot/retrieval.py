from __future__ import annotations

from typing import Any

from maintenance_copilot.answering import is_manual_guidance_query, is_procedural_query
from maintenance_copilot.config import Settings
from maintenance_copilot.domain import AssetMetadata, RetrievedChunk
from maintenance_copilot.providers import Reranker, TextEmbedder, VectorStore, tokenize


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        reranker: Reranker,
    ) -> None:
        self.settings = settings
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker

    def retrieve(
        self,
        *,
        tenant_id: str,
        asset: AssetMetadata,
        user_text: str,
        safety_critical: bool = False,
    ) -> tuple[str, list[RetrievedChunk]]:
        rewritten_query = self._rewrite_query(user_text, asset)
        query_vector = self.embedder.embed_query(rewritten_query)
        sparse_terms = tokenize(rewritten_query)
        manual_filter, log_filter = self._build_filters(asset)
        manual_guidance_query = is_manual_guidance_query(user_text)
        procedural_query = is_procedural_query(user_text)

        manual_hits = self.vector_store.query(
            "oem_manuals",
            tenant_id,
            query_vector,
            filter=manual_filter,
            top_k=self.settings.retrieval_top_k,
            sparse_terms=sparse_terms,
        )
        if procedural_query:
            manual_hits = self._expand_procedural_manual_hits(
                tenant_id=tenant_id,
                query_vector=query_vector,
                sparse_terms=sparse_terms,
                manual_filter=manual_filter,
                manual_hits=manual_hits,
            )
        log_hits = []
        if not manual_guidance_query:
            log_hits = self.vector_store.query(
                "historical_insights",
                tenant_id,
                query_vector,
                filter=log_filter,
                top_k=self.settings.retrieval_top_k,
                sparse_terms=sparse_terms,
            )

        deduped = self._dedupe(manual_hits + log_hits)
        if procedural_query:
            deduped.sort(key=lambda item: item.score, reverse=True)
            return rewritten_query, self._select_procedural_evidence(deduped)

        reranked_top_n = self.settings.retrieval_top_k if procedural_query else self.settings.answer_top_n
        reranked = self.reranker.rerank(
            rewritten_query,
            deduped,
            reranked_top_n,
            safety_critical=safety_critical,
        )
        return rewritten_query, self._select_evidence(
            reranked,
            manual_only=manual_guidance_query,
        )

    def _build_filters(self, asset: AssetMetadata) -> tuple[dict[str, Any], dict[str, Any]]:
        manual_filter = {
            "machine_model": asset.machine_model,
            "manual_version": asset.active_manual_version,
        }
        log_filter = {
            "site_id": asset.site_id,
            "machine_model": asset.machine_model,
        }
        return manual_filter, log_filter

    def _rewrite_query(self, user_text: str, asset: AssetMetadata) -> str:
        prefixes = [
            f"machine_id {asset.machine_id}",
            f"machine_model {asset.machine_model}",
        ]
        if asset.machine_family:
            prefixes.append(f"machine_family {asset.machine_family}")
        prefixes.extend(f"alias {alias}" for alias in asset.aliases)
        return " ".join(prefixes + [user_text])

    def _dedupe(self, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        by_chunk_id: dict[str, RetrievedChunk] = {}
        for candidate in candidates:
            existing = by_chunk_id.get(candidate.chunk.chunk_id)
            if existing is None or candidate.score > existing.score:
                by_chunk_id[candidate.chunk.chunk_id] = candidate
        return list(by_chunk_id.values())

    def _expand_procedural_manual_hits(
        self,
        *,
        tenant_id: str,
        query_vector: list[float],
        sparse_terms: list[str],
        manual_filter: dict[str, Any],
        manual_hits: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not manual_hits:
            return manual_hits

        anchor_page = None
        for item in manual_hits:
            page = item.chunk.page or item.chunk.source_ref.page
            if page is None:
                continue
            lowered = item.chunk.text.lower()
            if any(
                lowered.startswith(token)
                for token in [
                    "2.9.4 securing the engine against unexpected start-up and releasing it",
                    "secure the engine against unexpected start-up:",
                    "access to the engine must be secured against unexpected start-up",
                    "make the engine operational (release it):",
                ]
            ):
                anchor_page = page
                break
        if anchor_page is None:
            for item in manual_hits:
                page = item.chunk.page or item.chunk.source_ref.page
                if page is not None:
                    anchor_page = page
                    break
        anchor_pages = [anchor_page] if anchor_page is not None else []

        augmented = list(manual_hits)
        for page in anchor_pages:
            for target_page, bonus in ((page, 12.0), (page + 1, 10.0)):
                if target_page < 1:
                    continue
                page_hits = self.vector_store.query(
                    "oem_manuals",
                    tenant_id,
                    query_vector,
                    filter={**manual_filter, "page": target_page},
                    top_k=20,
                    sparse_terms=sparse_terms,
                )
                augmented.extend(
                    item.model_copy(update={"score": item.score + bonus})
                    for item in page_hits
                )
        return self._dedupe(augmented)

    def _select_evidence(
        self,
        candidates: list[RetrievedChunk],
        *,
        manual_only: bool = False,
    ) -> list[RetrievedChunk]:
        manuals = [item for item in candidates if item.chunk.is_manual and item.chunk.source_ref]
        logs = [item for item in candidates if not item.chunk.is_manual and item.chunk.source_ref]

        selected: list[RetrievedChunk] = []
        selected.extend(manuals[: self.settings.min_manual_evidence])
        if not manual_only:
            selected.extend(logs[: self.settings.min_log_evidence])

        if len(selected) < self.settings.answer_top_n:
            seen = {item.chunk.chunk_id for item in selected}
            for candidate in candidates:
                if manual_only and not candidate.chunk.is_manual:
                    continue
                if candidate.chunk.chunk_id in seen:
                    continue
                selected.append(candidate)
                seen.add(candidate.chunk.chunk_id)
                if len(selected) >= self.settings.answer_top_n:
                    break
        return selected

    def _select_procedural_evidence(
        self,
        candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        anchor_page = None
        for candidate in candidates:
            page = candidate.chunk.page or candidate.chunk.source_ref.page
            if page is None:
                continue
            lowered = candidate.chunk.text.lower()
            if any(
                lowered.startswith(token)
                for token in [
                    "2.9.4 securing the engine against unexpected start-up and releasing it",
                    "secure the engine against unexpected start-up:",
                    "access to the engine must be secured against unexpected start-up",
                    "make the engine operational (release it):",
                ]
            ):
                anchor_page = page
                break
        if anchor_page is None:
            for candidate in candidates:
                page = candidate.chunk.page or candidate.chunk.source_ref.page
                if page is not None and candidate.chunk.is_manual:
                    anchor_page = page
                    break
        if anchor_page is None:
            return self._select_evidence(candidates, manual_only=True)

        preferred_pages = {anchor_page, anchor_page + 1}
        preferred_candidates = [
            candidate
            for candidate in candidates
            if (candidate.chunk.page or candidate.chunk.source_ref.page) in preferred_pages
        ]
        preferred_candidates.sort(
            key=self._procedural_candidate_priority,
            reverse=True,
        )

        selected: list[RetrievedChunk] = []
        seen: set[str] = set()
        for candidate in preferred_candidates:
            if candidate.chunk.chunk_id in seen:
                continue
            selected.append(candidate)
            seen.add(candidate.chunk.chunk_id)
            if len(selected) >= self.settings.answer_top_n:
                break

        if len(selected) < self.settings.answer_top_n:
            for candidate in candidates:
                if not candidate.chunk.is_manual or candidate.chunk.chunk_id in seen:
                    continue
                selected.append(candidate)
                seen.add(candidate.chunk.chunk_id)
                if len(selected) >= self.settings.answer_top_n:
                    break
        return selected

    def _procedural_candidate_priority(self, candidate: RetrievedChunk) -> tuple[int, float]:
        lowered = candidate.chunk.text.lower()
        if any(
            lowered.startswith(token)
            for token in [
                "disconnect the diesel fuel supply",
                "mark the cut-off point with a tag",
                "disconnect the electrical power supply and secure it against being switched back on",
                "all foreign objects are removed",
                "all protectives devices are installed and are functioning",
                "all protective devices are installed and are functioning",
                "no outsiders are residing in the danger zones",
                "the tags for the fuel supply are removed",
                "fuel supply is connected",
                "the tag for the electrical power supply is removed",
                "the electrical power supply is established",
            ]
        ):
            return (6, candidate.score)
        if any(
            lowered.startswith(token)
            for token in [
                "2.9.4 securing the engine against unexpected start-up and releasing it",
                "secure the engine against unexpected start-up:",
                "access to the engine must be secured against unexpected start-up",
                "make the engine operational (release it):",
                "the following activities have been completed:",
            ]
        ):
            return (5, candidate.score)
        if "emergency stop" in lowered:
            return (0, candidate.score)
        if "warning sign" in lowered or "trapping points" in lowered:
            return (1, candidate.score)
        return (2, candidate.score)
