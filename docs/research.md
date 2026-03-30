# Research Notes

This file captures the vendor and framework choices used by the implementation in this repository. All cited claims below were checked on March 29, 2026 against official vendor documentation or official repositories.

## 1. Embedding strategy

Decision:

- Use a text-first embedding backbone for both manuals and historical logs.
- Keep a manual-only multimodal side path for diagrams, wiring maps, and other irreducibly visual content.

Why:

- Vertex AI’s multimodal embeddings page explicitly says: for text-only embedding use cases, use the text embeddings API instead.
- The same page documents `gemini-embedding-2-preview` as preview-only, which is not a good default for a production path.
- Google’s official Gemini Embedding 2 launch post and Vertex docs both support configurable output dimensionality, which makes a lower-dimensional primary index a defensible cost-control choice.

Practical default:

- Primary text index: 768 dimensions.
- Multimodal side index: 1536 dimensions.
- Increase only if evaluation shows recall loss on diagram-heavy tenants.

Sources:

- [Vertex AI multimodal embeddings](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-multimodal-embeddings)
- [Vertex AI text embeddings](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/embeddings/get-text-embeddings)
- [Google blog: Gemini Embedding 2](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2/)

## 2. Tenant isolation

Decision:

- Derive `tenant_id` only from the verified Okta access token.
- Enforce vector isolation with namespace-per-tenant.

Why:

- Okta’s custom authorization server flow supports custom claims in access tokens.
- Okta’s API Access Management guidance is explicit that custom authorization servers are the right place for custom scopes and claims.
- Pinecone’s documentation recommends namespaces for multitenancy and explicitly calls out using separate namespaces for tenant isolation.

Practical default:

- Reject requests where `tenant_id` is absent from the verified token.
- Never accept `tenant_id` from the request body for retrieval or writes.
- Use a single namespace string equal to the verified `tenant_id`.

Sources:

- [Okta API Access Management](https://developer.okta.com/docs/concepts/api-access-management/)
- [Okta token customization guide](https://developer.okta.com/docs/guides/customize-tokens-returned-from-okta/main/)
- [Pinecone database limits and namespace guidance](https://docs.pinecone.io/reference/api/database-limits)
- [Pinecone manage cost guide](https://docs.pinecone.io/guides/manage-cost/manage-cost)

## 3. Retrieval and reranking

Decision:

- Retrieve from manuals and logs independently inside the same tenant namespace.
- Merge, dedupe, rerank, and then enforce a citation-first evidence policy.

Why:

- Pinecone supports namespace scoping plus metadata filters.
- Pinecone’s docs also warn that large shared-namespace filters increase query cost and suggest namespaces for tenant isolation.
- Google’s ranking API docs position the ranking API as a standalone semantic reranker with very low latency and state-of-the-art relevance scoring.

Practical default:

- Dense retrieval everywhere.
- Sparse lexical boosting for fault codes, part numbers, and exact identifiers when available.
- Default rerank tier: `semantic-ranker-fast@latest`.
- Fallback rerank tier: `semantic-ranker-default@latest` when confidence is weak or the issue is safety-critical.

Sources:

- [Pinecone hybrid search](https://docs.pinecone.io/guides/search/hybrid-search)
- [Pinecone metadata filters](https://docs.pinecone.io/guides/search/filter-by-metadata)
- [Vertex AI ranking API](https://docs.cloud.google.com/generative-ai-app-builder/docs/ranking)
- [Vertex AI RAG retrieval and ranking](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/retrieval-and-ranking)

## 4. Orchestration model

Decision:

- Use a deterministic, resumable troubleshooting graph rather than a freeform autonomous loop.

Why:

- LangGraph’s workflow guidance draws a clean distinction between workflows with predetermined code paths and agents with dynamic tool usage.
- Troubleshooting playbooks benefit from predetermined steps, durable state, and auditable transitions.

Practical default:

- `load_context -> clarify_if_needed -> retrieve -> rerank -> compose -> persist -> escalate_if_needed`

Sources:

- [LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

## 5. Vector backends

Decision:

- Default recommendation: Pinecone for fastest safe SaaS rollout.
- Keep the internal retrieval abstraction narrow so pgvector or Weaviate can be swapped in later.

Why:

- Pinecone has explicit namespace guidance for multitenancy and predictable hosted operations.
- pgvector’s README clearly documents the HNSW versus IVFFlat tradeoff.
- Weaviate remains a valid alternative when teams want heavier database control and shard-level tenancy behavior.

Sources:

- [pgvector README](https://github.com/pgvector/pgvector)
- [Weaviate multi-tenancy](https://docs.weaviate.io/weaviate/manage-collections/multi-tenancy)
- [Weaviate ACORN filter strategy](https://docs.weaviate.io/weaviate/concepts/filtering)
