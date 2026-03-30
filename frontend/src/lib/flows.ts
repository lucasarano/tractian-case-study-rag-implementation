import type { Node, Edge } from "@xyflow/react";

// ── Architecture overview nodes & edges ──

export const archNodes: Node[] = [
  {
    id: "frontend",
    type: "archNode",
    position: { x: 50, y: 200 },
    data: {
      label: "React Frontend",
      category: "frontend",
      description: "Vite SPA",
      summary:
        "The SPA that engineers interact with. It now centers the experience around architecture exploration and the RAG workspace.",
      detail: {
        role: "Where engineers inspect the system architecture and operate the RAG workspace. It handles routing, the PDF-backed troubleshooting interface, and this architecture diagram.",
        importance:
          "Technicians need answers fast. The UI shows real-time pipeline progress and keeps the workflow tight so nobody's waiting around.",
        whyChosen:
          "Vite for fast builds, React for the interactive flow diagrams (React Flow), Tailwind for styling without fighting CSS.",
      },
    },
  },
  {
    id: "api",
    type: "archNode",
    position: { x: 320, y: 200 },
    data: {
      label: "FastAPI",
      category: "api",
      description: "REST API + Auth",
      summary:
        "REST API between the frontend and everything else. Handles auth, validation, and routing.",
      detail: {
        role: "Routes requests to the right service: kicks off ingestion pipelines, proxies troubleshooting to LangGraph, and validates everything with Pydantic.",
        importance:
          "One entry point means auth and validation happen in one place. Async design lets it handle multiple long-running jobs without blocking.",
        whyChosen:
          "Native async, auto-generated OpenAPI docs, and Pydantic validation. Good fit for a backend that calls a lot of external APIs.",
      },
    },
  },
  {
    id: "manual_ingest",
    type: "archNode",
    position: { x: 600, y: 60 },
    data: {
      label: "Manual Ingest",
      category: "ingest",
      description: "PDF → Chunks → Embed",
      link: "/rag",
      summary:
        "Takes OEM manuals from PDF to vector embeddings through Document AI, chunking, and Vertex AI.",
      detail: {
        role: "Runs uploaded PDFs through OCR, chunking, embedding, and indexing. Each stage is independent so failures don't take down the whole pipeline.",
        importance:
          "Manuals are the main knowledge source. If extraction or chunking is bad, retrieval is bad, and the diagnoses suffer.",
        whyChosen:
          "Dedicated pipeline gives control over chunk boundaries, metadata, and error recovery at each stage. Industrial PDFs need that.",
      },
    },
  },
  {
    id: "log_ingest",
    type: "archNode",
    position: { x: 600, y: 340 },
    data: {
      label: "Log Ingest",
      category: "ingest",
      description: "Markdown → Normalize → Embed",
      link: "/rag",
      summary:
        "Parses maintenance logs into structured records, embeds them, and indexes for similarity search.",
      detail: {
        role: "Parses freeform logs, extracts structured fields, embeds them, and stores in Pinecone. Low-confidence records get normalized by Gemini.",
        importance:
          "Past incidents show what actually broke and what actually fixed it. Without logs, the system only knows what the manual says.",
        whyChosen:
          "Separate from manual ingestion because logs have different structure, metadata, and dedup needs.",
      },
    },
  },
  {
    id: "troubleshoot",
    type: "archNode",
    position: { x: 600, y: 200 },
    data: {
      label: "Troubleshoot Graph",
      category: "graph",
      description: "LangGraph 5-node workflow",
      link: "/rag",
      summary:
        "LangGraph state machine that handles retrieval, reasoning, follow-ups, and diagnosis in a 5-node workflow.",
      detail: {
        role: "5-node workflow: load context, retrieve from manuals and logs, ask follow-ups if needed, compose a diagnosis, and save the session.",
        importance:
          "This is where the actual reasoning happens. A graph lets it loop back for clarifications or skip steps, which a linear chain can't do.",
        whyChosen:
          "LangGraph supports cycles, conditional edges, and checkpointing. Conversations can span multiple sessions without losing state.",
      },
    },
  },
  {
    id: "docai",
    type: "archNode",
    position: { x: 920, y: 0 },
    data: {
      label: "Document AI",
      category: "gcp",
      description: "Layout + OCR",
      summary:
        "Extracts text from PDFs with layout awareness. Preserves tables, headers, and reading order.",
      detail: {
        role: "Runs OCR that understands page layout. Tables, headers, lists, and reading order come through intact instead of getting flattened into a text blob.",
        importance:
          "Manuals have complex layouts. If you lose table structure or heading hierarchy during extraction, the chunks downstream are useless.",
        whyChosen:
          "Beats Tesseract and PyPDF on industrial docs. Handles multi-column pages, diagrams, and technical tables well.",
      },
    },
  },
  {
    id: "vertexai",
    type: "archNode",
    position: { x: 920, y: 120 },
    data: {
      label: "Vertex AI",
      category: "gcp",
      description: "Gemini + Embeddings",
      summary:
        "Handles text generation (Gemini) and embedding creation. The AI layer for the whole system.",
      detail: {
        role: "Text generation via Gemini for reasoning and responses. Embedding generation for both manual chunks and log entries during ingestion.",
        importance:
          "Embedding quality controls how good retrieval is. Generation quality controls how useful diagnoses are. Everything intelligent goes through here.",
        whyChosen:
          "Managed Gemini access with IAM integration and safety filters. No model hosting to deal with, runs under Google Cloud's SLA.",
      },
    },
  },
  {
    id: "ranking",
    type: "archNode",
    position: { x: 920, y: 240 },
    data: {
      label: "Ranking API",
      category: "gcp",
      description: "Discovery Engine",
      summary:
        "Re-ranks retrieved chunks using cross-encoder scoring to improve precision over raw vector similarity.",
      detail: {
        role: "Takes the chunks from Pinecone and re-scores them with a cross-encoder so the most relevant ones end up in the LLM's context window.",
        importance:
          "Vector search returns roughly relevant results. Re-ranking sharpens that so the LLM gets the best context, not just the closest vectors.",
        whyChosen:
          "Gets strong relevance scoring without needing a custom fine-tuned model or extra infrastructure.",
      },
    },
  },
  {
    id: "pinecone",
    type: "archNode",
    position: { x: 920, y: 360 },
    data: {
      label: "Pinecone",
      category: "vector",
      description: "oem_manuals + historical_insights",
      summary:
        "Vector database with two namespaces: oem_manuals and historical_insights. Supports filtered similarity search.",
      detail: {
        role: "Stores embeddings in two namespaces: oem_manuals for manual chunks and historical_insights for incident logs. Metadata filters let you scope queries by equipment, date, etc.",
        importance:
          "RAG needs fast vector search. Sub-100ms queries keep the troubleshooting chat responsive even as the knowledge base grows.",
        whyChosen:
          "Serverless tier means no infra to manage. Auto-scales, low latency, and metadata filtering works out of the box.",
      },
    },
  },
  {
    id: "postgres",
    type: "archNode",
    position: { x: 320, y: 400 },
    data: {
      label: "PostgreSQL",
      category: "infra",
      description: "Sessions, Jobs, Checkpoints",
      summary:
        "Stores sessions, jobs, and LangGraph checkpoints. The transactional backbone.",
      detail: {
        role: "Stores troubleshooting sessions, ingestion jobs, user data, and LangGraph checkpoints. All stateful operations go through here.",
        importance:
          "ACID compliance means no session or job state gets lost on crashes or restarts. Important when technicians depend on it mid-shift.",
        whyChosen:
          "Proven reliability, good tooling (Alembic, SQLAlchemy), and native LangGraph checkpoint support via langgraph-checkpoint-postgres.",
      },
    },
  },
  {
    id: "redis",
    type: "archNode",
    position: { x: 320, y: 50 },
    data: {
      label: "Redis",
      category: "infra",
      description: "Conversation cache",
      summary:
        "In-memory cache for conversation context and session tokens. Sub-millisecond reads.",
      detail: {
        role: "Caches conversation context, session tokens, and hot metadata between requests. Keeps multi-turn conversations fast.",
        importance:
          "Cuts database load and response latency for repeated lookups during conversations.",
        whyChosen:
          "Sub-millisecond reads, TTL for session expiry, and easy to run as a Docker sidecar.",
      },
    },
  },
];

export const archEdges: Edge[] = [
  { id: "e-fe-api", source: "frontend", target: "api", animated: true },
  { id: "e-api-manual", source: "api", target: "manual_ingest" },
  { id: "e-api-log", source: "api", target: "log_ingest" },
  { id: "e-api-trouble", source: "api", target: "troubleshoot" },
  { id: "e-api-pg", source: "api", target: "postgres" },
  { id: "e-api-redis", source: "api", target: "redis" },
  { id: "e-manual-docai", source: "manual_ingest", target: "docai" },
  { id: "e-manual-vertex", source: "manual_ingest", target: "vertexai" },
  { id: "e-manual-pine", source: "manual_ingest", target: "pinecone" },
  { id: "e-log-vertex", source: "log_ingest", target: "vertexai" },
  { id: "e-log-pine", source: "log_ingest", target: "pinecone" },
  { id: "e-trouble-vertex", source: "troubleshoot", target: "vertexai" },
  { id: "e-trouble-rank", source: "troubleshoot", target: "ranking" },
  { id: "e-trouble-pine", source: "troubleshoot", target: "pinecone" },
];
