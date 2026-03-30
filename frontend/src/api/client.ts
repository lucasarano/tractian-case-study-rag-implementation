import type {
  AnswerEnvelope,
  AnswerRequest,
  CreateSessionRequest,
  HealthResponse,
  IngestLogRequest,
  IngestManualRequest,
  IngestResult,
  ManualIngestJobRecord,
  SessionRecord,
} from "./types";

const AUTH_TOKEN = "dev:tech-001@companyA";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${AUTH_TOKEN}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export const api = {
  healthz: () => request<HealthResponse>("/healthz"),

  createSession: (body: CreateSessionRequest) =>
    request<SessionRecord>("/v1/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  answer: (body: AnswerRequest) =>
    request<AnswerEnvelope>("/v1/copilot/answer", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  ingestManual: (body: IngestManualRequest) =>
    request<IngestResult>("/v1/ingest/manuals", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  ingestManualUpload: async (
    file: File,
    metadata: Omit<IngestManualRequest, "pdf_path" | "pages">,
  ): Promise<IngestResult> => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_id", metadata.doc_id);
    form.append("manufacturer", metadata.manufacturer);
    form.append("machine_model", metadata.machine_model);
    form.append("manual_version", metadata.manual_version);
    if (metadata.machine_family) form.append("machine_family", metadata.machine_family);
    if (metadata.activate_version !== undefined)
      form.append("activate_version", String(metadata.activate_version));

    const res = await fetch("/v1/ingest/manuals/upload", {
      method: "POST",
      headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
      body: form,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${body}`);
    }
    return res.json();
  },

  createManualJob: (body: IngestManualRequest) =>
    request<ManualIngestJobRecord>("/v1/ingest/manuals/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getManualJob: (jobId: string) =>
    request<ManualIngestJobRecord>(`/v1/ingest/manuals/jobs/${jobId}`),

  ingestLog: (body: IngestLogRequest) =>
    request<IngestResult>("/v1/ingest/logs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
