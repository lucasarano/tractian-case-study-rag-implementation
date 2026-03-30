# Tractian Case Study RAG Implementation

This repository is a maintenance copilot demo built around RAG for industrial equipment.

It combines:

- OEM manual retrieval
- historical maintenance logs
- a FastAPI backend
- a React/Vite frontend
- Docker-based local startup

The current demo focuses on a Kohler generator manual subset and a simple UI for exploring the architecture and the RAG workflow.

## Tech Used

- FastAPI
- LangGraph
- PostgreSQL
- Redis
- Pinecone
- Google Document AI
- Gemini
- React
- Vite
- Docker Compose

## What Docker Starts

`docker compose up --build` starts six services:

- `postgres`: application database
- `redis`: cache and worker coordination
- `migrate`: runs `alembic upgrade head` once
- `app`: FastAPI server on port `8000`
- `worker`: background manual-ingest worker
- `frontend`: Vite dev server on port `5173`

How it works:

- `app`, `worker`, and `migrate` are built from the repo `Dockerfile`
- the backend image installs the Python app and runs from `/app`
- the repo is mounted into the backend containers, so code changes are visible inside the containers
- `frontend` runs in a separate `node:22-alpine` container
- the frontend mounts `./frontend`, installs packages, and serves the app with Vite
- the frontend talks to the backend through `VITE_API_URL=http://app:8000`

## Environment Variables

Start from the template:

```bash
cp .env.example .env
```

For local Docker startup, keep these set in `.env`:

- `COPILOT_RUNTIME_ENV=local`
- `COPILOT_AUTH_MODE=dev`
- `COPILOT_VECTOR_BACKEND=pinecone`
- `COPILOT_GENERATION_BACKEND=gemini`
- `COPILOT_DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/maintenance_copilot`
- `COPILOT_REDIS_URL=redis://redis:6379/0`
- `COPILOT_GOOGLE_PROJECT`
- `COPILOT_GOOGLE_LOCATION=us-central1`
- `COPILOT_DOCUMENTAI_LOCATION=us`
- `COPILOT_DOCUMENTAI_LAYOUT_PROCESSOR_ID`
- `COPILOT_DOCUMENTAI_OCR_PROCESSOR_ID` optional
- `GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/google-service-account.json`
- `COPILOT_PINECONE_API_KEY`
- `COPILOT_PINECONE_MANUAL_INDEX`
- `COPILOT_PINECONE_LOG_INDEX`

Recommended local credential path:

- put the Google service account JSON at `secrets/google-service-account.json`
- keep `GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/google-service-account.json` in `.env`

## Run Locally

1. Copy `.env.example` to `.env`
2. Fill in the Google and Pinecone values
3. Make sure the Google credentials file exists at `secrets/google-service-account.json`
4. Start the stack:

```bash
docker compose up --build
```

If you want it in the background:

```bash
docker compose up --build -d
```

Open:

- UI: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Health check: [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)

To stop everything:

```bash
docker compose down
```

To rebuild after dependency or Dockerfile changes:

```bash
docker compose up --build
```

To restart containers after normal code changes:

```bash
docker compose restart app frontend worker
```

## Interacting With The App

Use the UI at [http://127.0.0.1:5173](http://127.0.0.1:5173).

In local mode, auth is simulated with bearer tokens in this format:

```text
Authorization: Bearer dev:<user_id>@<tenant_id>
```

Example:

```text
Authorization: Bearer dev:tech-001@companyA
```

Seed assets are loaded automatically from `fixtures/assets.json` when `COPILOT_RUNTIME_ENV=local`.
