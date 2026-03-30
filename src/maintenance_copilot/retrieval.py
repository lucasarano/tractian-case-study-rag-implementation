from __future__ import annotations

from typing import Any

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

        manual_hits = self.vector_store.query(
            "oem_manuals",
            tenant_id,
            query_vector,
            filter=manual_filter,
            top_k=self.settings.retrieval_top_k,
            sparse_terms=sparse_terms,
        )
        log_hits = self.vector_store.query(
            "historical_insights",
            tenant_id,
            query_vector,
            filter=log_filter,
            top_k=self.settings.retrieval_top_k,
            sparse_terms=sparse_terms,
        )

        deduped = self._dedupe(manual_hits + log_hits)
        reranked = self.reranker.rerank(
            rewritten_query,
            deduped,
            self.settings.answer_top_n,
            safety_critical=safety_critical,
        )
        return rewritten_query, self._select_evidence(reranked)

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

    def _select_evidence(self, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        manuals = [item for item in candidates if item.chunk.is_manual and item.chunk.source_ref]
        logs = [item for item in candidates if not item.chunk.is_manual and item.chunk.source_ref]

        selected: list[RetrievedChunk] = []
        selected.extend(manuals[: self.settings.min_manual_evidence])
        selected.extend(logs[: self.settings.min_log_evidence])

        if len(selected) < self.settings.answer_top_n:
            seen = {item.chunk.chunk_id for item in selected}
            for candidate in candidates:
                if candidate.chunk.chunk_id in seen:
                    continue
                selected.append(candidate)
                seen.add(candidate.chunk.chunk_id)
                if len(selected) >= self.settings.answer_top_n:
                    break
        return selected
