# Operational Runbook

## Startup

1. Fill [.env.example](/Users/lucas/Developer/tractian-implementation/.env.example) into `.env`.
2. Ensure the Pinecone manual and log indexes already exist.
3. Ensure the Discovery Engine API is enabled in the Google Cloud project for Vertex Ranking API.
4. Start the stack with `docker compose up --build`.
5. Confirm:
   - `GET /healthz` returns `ok`
   - `GET /readyz` returns `ready`
   - the `worker` container is running

## Manual Ingest

Preferred path:

1. `POST /v1/ingest/manuals/jobs`
2. Poll `GET /v1/ingest/manuals/jobs/{job_id}`
3. The worker claims pending jobs and marks them `running`, `succeeded`, or `failed`

Operational notes:

- manuals are chunked into section, table-row, and figure-semantic chunks
- active manual version bindings are updated when `activate_version=true`
- OCR is only invoked when layout extraction is too sparse
- Gemini visual summarization is only used for visually important, low-text manual pages

## Log Ingest

Use `POST /v1/ingest/logs` for new incidents.

Operational notes:

- rules extract timestamps, ids, fault codes, part numbers, issues, and outcomes first
- Gemini fallback runs only below the configured confidence threshold
- every log summary retains raw path plus line-range evidence spans for citation

## Troubleshooting Sessions

Every answer request runs through the LangGraph workflow:

- load or create session
- resolve asset context
- ask follow-up when asset context is insufficient
- retrieve OEM and historical evidence
- compose a strict JSON answer
- persist session state and cached summary
- optionally write a work-order note and escalate

## Safety Guardrails

- no procedural step may be emitted without an OEM citation
- logs can strengthen suspicion and context, but cannot authorize procedure
- tenant scope comes only from verified auth, not from request payloads
- high-urgency low-confidence cases are flagged for escalation

## Troubleshooting Failures

If `readyz` is not ready:

- `database=error:*`: check Postgres connectivity and migration status
- `redis=error:*`: check Redis availability and the configured URL
- app boot failures before `readyz`: validate `.env` against startup requirements in [src/maintenance_copilot/config.py](/Users/lucas/Developer/tractian-implementation/src/maintenance_copilot/config.py)

If manual jobs fail:

- inspect the `manual_ingest_jobs` table
- check worker logs
- validate the Document AI processor id and Google project/location
- confirm the source PDF path or JSON seed payload is accessible inside the container

If retrieval quality is weak:

- verify the active manual version binding for the model
- confirm the tenant namespace and metadata filters match the asset
- inspect whether relevant identifiers are present for sparse lexical boosting
- review rerank thresholds and evidence caps
