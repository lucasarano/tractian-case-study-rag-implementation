# Maintenance Copilot

Production-oriented two-lane RAG troubleshooting copilot for industrial maintenance.

The implementation follows the earlier plan:

- OEM manuals are authoritative for procedure and safety.
- Historical logs are contextual evidence only.
- Retrieval is text-first across both lanes, with selective visual understanding for manual pages through Document AI plus Gemini summarization.
- Tenant scope is derived from verified identity, never from request payloads.
- Troubleshooting runs through a deterministic LangGraph workflow with persisted checkpoints and session state.

## Architecture

Core stack:

- FastAPI API service
- LangGraph state graph with Postgres-backed checkpoints
- Postgres for durable sessions, asset catalog, manual version bindings, ingest jobs, and local work-order notes
- Redis for short-lived conversation cache
- Vertex AI `gemini-embedding-001` for dense text embeddings
- Document AI Layout Parser for manual page regionization
- Gemini 2.5 Flash for visual summarization, low-confidence log normalization fallback, and structured answer generation
- Vertex Ranking API with `semantic-ranker-fast@latest` and `semantic-ranker-default@latest`
- Pinecone dual-index retrieval with namespace-per-tenant isolation
- Vertex Ranking API for second-stage reranking
- Okta JWT verification outside local development

Two corpora per tenant:

- `oem_manuals`
- `historical_insights`

Ingest lanes:

- Manuals: Document AI parse -> deterministic text/table extraction -> selective OCR -> selective Gemini visual summarization -> chunk -> embed -> Pinecone upsert
- Logs: rules-first extraction -> Gemini fallback only below confidence threshold -> summary chunk + evidence span chunks -> embed -> Pinecone upsert

Troubleshooting graph:

- `load_context`
- `ask_followup` when asset context is insufficient
- `retrieve`
- `compose`
- `persist`

Policy rules enforced in code:

- no tenant scope from client input
- no procedural step without OEM citation
- logs may support, but never authorize, safety instructions
- manual versions can be bound per model/family and used in retrieval filtering

## Local Start

1. Copy the environment file and fill the managed-provider credentials:

```bash
cp .env.example .env
```

2. Create the Pinecone indexes referenced by `.env` before startup.

3. Enable the Discovery Engine API in the same Google Cloud project, because Vertex Ranking API depends on it.

4. Provide Google Application Default Credentials to the containers.

Recommended local approach:

- put the service-account JSON somewhere inside the repo, for example `secrets/google-service-account.json`
- set `GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/google-service-account.json` in `.env`

Recommended index settings:

- metric: `dotproduct`
- dimensions: `768`
- hybrid search enabled in the retrieval path through dense vectors plus sparse lexical boosting

5. Start the full local stack:

```bash
docker compose up --build
```

This starts:

- `postgres`
- `redis`
- `migrate`
- `app`
- `worker`

The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

Local auth is simulated by default with bearer tokens in the form:

```text
dev:<user_id>@<tenant_id>
```

Example:

```text
Authorization: Bearer dev:tech-001@companyA
```

## Required Environment

The managed local path expects these values in `.env`:

- `COPILOT_RUNTIME_ENV=local`
- `COPILOT_AUTH_MODE=dev`
- `COPILOT_VECTOR_BACKEND=pinecone`
- `COPILOT_GENERATION_BACKEND=gemini`
- `COPILOT_DATABASE_URL`
- `COPILOT_REDIS_URL`
- `COPILOT_GOOGLE_PROJECT`
- `COPILOT_GOOGLE_LOCATION`
- `COPILOT_DOCUMENTAI_LAYOUT_PROCESSOR_ID`
- `COPILOT_DOCUMENTAI_OCR_PROCESSOR_ID` optional but recommended
- `GOOGLE_APPLICATION_CREDENTIALS` for Vertex AI and Document AI authentication inside the containers
- `COPILOT_PINECONE_API_KEY`
- `COPILOT_PINECONE_MANUAL_INDEX`
- `COPILOT_PINECONE_LOG_INDEX`

Outside local development, switch to:

- `COPILOT_AUTH_MODE=okta`
- `COPILOT_OKTA_ISSUER`
- `COPILOT_OKTA_AUDIENCE`

## Database Setup

App tables are migrated through Alembic:

```bash
alembic upgrade head
```

The initial migration creates:

- `copilot_sessions`
- `assets`
- `manual_model_bindings`
- `manual_ingest_jobs`
- `work_order_notes`

LangGraph checkpoint tables are created by the Postgres checkpointer during service startup.

## API Surface

- `GET /healthz`
- `GET /readyz`
- `POST /v1/sessions`
- `POST /v1/copilot/answer`
- `POST /v1/ingest/logs`
- `POST /v1/ingest/manuals`
- `POST /v1/ingest/manuals/jobs`
- `GET /v1/ingest/manuals/jobs/{job_id}`

## Smoke Test

After `docker compose up --build`, run:

```bash
make smoke
```

The smoke flow:

- enqueues a manual ingest job using [fixtures/manual_job.json](/Users/lucas/Developer/tractian-implementation/fixtures/manual_job.json)
- waits for the worker to finish the job
- ingests [fixtures/log_incident.json](/Users/lucas/Developer/tractian-implementation/fixtures/log_incident.json)
- asks an overheating question
- asserts the answer contains both OEM and historical citations

Seed assets are loaded from [fixtures/assets.json](/Users/lucas/Developer/tractian-implementation/fixtures/assets.json) when `COPILOT_RUNTIME_ENV=local`.

## CLI

The repo includes a small operational CLI:

```bash
python -m maintenance_copilot.cli seed-assets
python -m maintenance_copilot.cli ingest-manual --path fixtures/manual_job.json --tenant-id companyA
python -m maintenance_copilot.cli enqueue-manual --path fixtures/manual_job.json --tenant-id companyA
python -m maintenance_copilot.cli ingest-log --path fixtures/log_incident.json --tenant-id companyA
python -m maintenance_copilot.cli process-manual-jobs --once
```

## Test and Lint

The automated suite runs in `test` mode with in-memory auth, vector, and generation fallbacks:

```bash
ruff check .
pytest -q
```

Current coverage includes:

- tenant enforcement
- citation validation
- OEM-required procedure gating
- low-confidence log normalization fallback
- readiness endpoint
- async manual ingest job lifecycle through the API

## Key Implementation Files

- API and container bootstrap: [src/maintenance_copilot/api.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/api.py)
- LangGraph orchestration and citation policy: [src/maintenance_copilot/orchestration.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/orchestration.py)
- Provider adapters: [src/maintenance_copilot/providers.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/providers.py)
- Ingest pipelines: [src/maintenance_copilot/ingest.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/ingest.py)
- Retrieval flow: [src/maintenance_copilot/retrieval.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/retrieval.py)
- Persistence layer: [src/maintenance_copilot/sessions.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/sessions.py)
- SQLAlchemy models: [src/maintenance_copilot/database.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/database.py)
- Worker: [src/maintenance_copilot/worker.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/worker.py)

## Docs

- Research notes: [docs/research.md](/Users/lucas/Developer/tractian-implementation/docs/research.md)
- Architecture decision record: [docs/adr/0001-two-lane-rag.md](/Users/lucas/Developer/tractian-implementation/docs/adr/0001-two-lane-rag.md)
- Operational runbook: [docs/runbook.md](/Users/lucas/Developer/tractian-implementation/docs/runbook.md)
