import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Regex,
  Gauge,
  Sparkles,
  Layers,
  Binary,
  DatabaseZap,
} from "lucide-react";
import { PipelineFlow, type PipelineStage } from "../components/pipeline/PipelineFlow";
import { MarkdownEditor } from "../components/shared/MarkdownEditor";
import { JsonViewer } from "../components/shared/JsonViewer";
import { StatusBadge } from "../components/shared/StatusBadge";
import { api } from "../api/client";
import type { IngestResult } from "../api/types";

const stages: PipelineStage[] = [
  {
    id: "parse",
    label: "Parse Markdown",
    description: "Read incident log",
    icon: FileText,
    detail: {
      what: "The log is split into individual incidents using date markers and horizontal rules. Each incident becomes its own record.",
      input: "Markdown Text",
      output: "Incident Records",
      tech: "Regex-based markdown splitter",
    },
  },
  {
    id: "rules",
    label: "Rules Extraction",
    description: "Regex + keyword match",
    icon: Regex,
    detail: {
      what: "Pattern matching pulls out structured fields: machine IDs, dates, technician names, SPN/FMI codes, parts replaced, root causes.",
      input: "Raw Incidents",
      output: "Structured Fields",
      tech: "30+ regex patterns + keyword dictionaries",
    },
  },
  {
    id: "confidence",
    label: "Confidence Check",
    description: "Threshold >= 0.75",
    icon: Gauge,
    detail: {
      what: "Each record gets a completeness score. If key fields are missing or unclear, the score drops below 0.75 and the record gets sent to Gemini for cleanup.",
      input: "Extracted Fields",
      output: "Confidence Score",
      tech: "Weighted field-coverage heuristic",
    },
  },
  {
    id: "gemini",
    label: "Gemini Normalize",
    description: "LLM fallback if low",
    icon: Sparkles,
    detail: {
      what: "Low-confidence records go to Gemini, which resolves ambiguous dates, fills in missing fields from context, and cleans up technician shorthand.",
      input: "Low-confidence Records",
      output: "Normalized Records",
      tech: "Gemini 2.0 Flash with structured output",
    },
  },
  {
    id: "chunks",
    label: "Summary + Spans",
    description: "Summary + evidence spans",
    icon: Layers,
    detail: {
      what: "Each incident gets a summary optimized for search, plus evidence spans: the exact quotes backing each field. Used for both retrieval and citation.",
      input: "Normalized Records",
      output: "Summaries + Spans",
      tech: "Extractive span alignment",
    },
  },
  {
    id: "embed",
    label: "Embedding",
    description: "Vertex AI 768-dim",
    icon: Binary,
    detail: {
      what: "Summaries become 768-dimensional vectors encoding failure mode, symptoms, and resolution for each incident.",
      input: "Summary Text",
      output: "768-dim Vectors",
      tech: "Vertex AI text-embedding-005",
    },
  },
  {
    id: "upsert",
    label: "Pinecone Upsert",
    description: "historical_insights index",
    icon: DatabaseZap,
    detail: {
      what: "Vectors go into the historical_insights namespace with metadata: machine ID, date, failure type, severity, resolution status. Filterable by equipment and time range.",
      input: "Vectors + Metadata",
      output: "Indexed Entries",
      tech: "Pinecone Serverless (us-east-1)",
    },
  },
];

const defaultMarkdown = `## FEB-03-2025 — UNPLANNED SHUTDOWN

**machine: GEN-KD27-003**
tech: R. Mendes + A. Costa

Generator tripped during weekly load test around 14:30. Black smoke observed from exhaust for ~10 seconds before auto-shutdown. ECU showed SPN 94 FMI 1 (fuel supply critical underpressure).

Checked fuel level — tank at 60%.
Opened primary fuel filter/water separator — found significant water accumulation, maybe 200mL.
DRAINED water separator completely.
Main fuel filter — clogged bad. Dark residue on filter element. Replaced with new Kohler OEM filter (P/N TP-11027).
Bled fuel system per manual sec 5.7.
Restarted — ran smooth, no smoke.

Root cause: water ingress in fuel tank vent cap was cracked. replaced vent cap.

---

## 25-APR-2025 generator alarm COOLANT TEMP HIGH

tech: A. Costa
GEN-KD27-003
09:45 — got alarm on SCADA, coolant temp spiked to 103\u00B0C during morning run

checked coolant level — LOW, about 4L below min!!
no visible external leaks on hoses or radiator
shut down and let cool
pressure tested cooling system — found pinhole leak on coolant pipe at thermostat housing, barely visible
replaced coolant pipe section + new thermostat gasket
refilled coolant (Kohler genuine pre-mixed 50/50, 8L added)
restarted — temp holding steady at 83\u00B0C under load

turnaround: 4.5 hrs to get part from warehouse

---

## 2025-09-28 — oil pressure alarm

GEN-KD27-003
tech: R Mendes

Low oil pressure warning at 2.0 bar during loaded run (spec min is 2.5 bar). Runtime: 1,241 hrs.
oil looked thin, possible fuel dilution???
oil sample taken — lab rush results pending

Update 09-30: lab results — fuel dilution at 4.7% (threshold is 3%).
cyl 3 injector leaking past return. Dribble leak causing fuel wash into oil.
replaced cyl 3 injector. full oil & filter change.
Oil pressure back to 4.0 bar at full load.`;

export default function LogIngest() {
  const [form, setForm] = useState({
    machine_id: "GEN-KD27-003",
    site_id: "plant-north",
    machine_model: "KD27V12",
    machine_family: "generator",
    path: "logs/2025/maintenance_log_2025.md",
  });
  const [markdown, setMarkdown] = useState(defaultMarkdown);
  const [activeStage, setActiveStage] = useState(-1);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const updateField = useCallback(
    (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value })),
    [],
  );

  const handleSubmit = useCallback(async () => {
    if (!markdown.trim() || !form.machine_id) return;
    setRunning(true);
    setError(null);
    setResult(null);

    const simulateStages = async () => {
      for (let i = 0; i < stages.length - 1; i++) {
        setActiveStage(i);
        await new Promise((r) => setTimeout(r, 500));
      }
    };
    const stageAnimation = simulateStages();

    try {
      const res = await api.ingestLog({
        machine_id: form.machine_id,
        site_id: form.site_id,
        machine_model: form.machine_model,
        machine_family: form.machine_family || undefined,
        path: form.path,
        markdown,
      });
      await stageAnimation;
      setActiveStage(stages.length);
      setResult(res);
    } catch (e) {
      await stageAnimation;
      setActiveStage(stages.length - 1);
      setError(e instanceof Error ? e.message : "Ingestion failed");
    } finally {
      setRunning(false);
    }
  }, [form, markdown]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-text-primary">Incident Log Ingestion</h1>
        <p className="mt-1.5 text-sm text-text-secondary">
          Paste technician incident logs in markdown. They'll be normalized, chunked, and indexed
          into the historical insights knowledge base.
        </p>
      </div>

      {/* Pipeline */}
      <div className="rounded-2xl bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Log Processing Pipeline
          </h2>
          {running && <StatusBadge status="running" label="Processing..." />}
          {result && <StatusBadge status="done" label={`${result.chunk_count} chunks`} />}
          {error && <StatusBadge status="error" label="Failed" />}
        </div>
        <PipelineFlow stages={stages} activeIndex={activeStage} error={!!error} className="h-52" />
      </div>

      {/* Input area */}
      <div className="grid grid-cols-2 gap-8">
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-primary">Incident Markdown</h3>
          <MarkdownEditor value={markdown} onChange={setMarkdown} rows={8} />
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Preview
            </p>
            <div className="font-mono text-xs leading-relaxed text-text-secondary whitespace-pre-wrap max-h-48 overflow-auto">
              {markdown || "No content"}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-primary">Log Metadata</h3>
          {[
            { key: "machine_id", label: "Machine ID", placeholder: "GEN-KD27-003" },
            { key: "site_id", label: "Site ID", placeholder: "plant-north" },
            { key: "machine_model", label: "Machine Model", placeholder: "KD27V12" },
            { key: "machine_family", label: "Machine Family", placeholder: "generator" },
            { key: "path", label: "Log Path", placeholder: "logs/2025/maintenance_log_2025.md" },
          ].map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="mb-1 block text-[11px] font-medium text-text-muted">{label}</label>
              <input
                value={form[key as keyof typeof form]}
                onChange={updateField(key)}
                placeholder={placeholder}
                className="w-full rounded-xl border border-border bg-white px-3.5 py-2 font-mono text-sm text-text-primary shadow-sm placeholder:text-text-muted focus:border-accent-amber focus:outline-none focus:ring-2 focus:ring-accent-amber/20 transition-shadow"
              />
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={running || !markdown.trim() || !form.machine_id}
        className="rounded-xl bg-accent-amber px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-accent-amber/90 hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {running ? "Processing..." : "Ingest Log"}
      </button>

      {/* Results */}
      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-accent-green/20 bg-accent-green/5 p-5"
          >
            <h3 className="mb-3 text-sm font-semibold text-accent-green">Log Ingested</h3>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <Stat label="Corpus" value={result.corpus} />
              <Stat label="Namespace" value={result.namespace} />
              <Stat label="Chunks" value={String(result.chunk_count)} />
            </div>
            <details className="group">
              <summary className="cursor-pointer text-xs text-text-muted hover:text-text-secondary transition-colors">
                View chunk IDs
              </summary>
              <div className="mt-2">
                <JsonViewer data={result.chunk_ids} maxHeight="12rem" />
              </div>
            </details>
          </motion.div>
        )}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-2xl border border-accent-red/20 bg-accent-red/5 p-5"
          >
            <h3 className="mb-1 text-sm font-semibold text-accent-red">Ingestion Failed</h3>
            <p className="font-mono text-xs text-accent-red/80">{error}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-bg-secondary p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</p>
      <p className="mt-0.5 font-mono text-sm font-semibold text-text-primary">{value}</p>
    </div>
  );
}
