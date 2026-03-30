import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileSearch,
  ScanText,
  Eye,
  Scissors,
  Binary,
  DatabaseZap,
  Upload,
} from "lucide-react";
import { PipelineFlow, type PipelineStage } from "../components/pipeline/PipelineFlow";
import { FileDropzone } from "../components/shared/FileDropzone";
import { JsonViewer } from "../components/shared/JsonViewer";
import { StatusBadge } from "../components/shared/StatusBadge";
import { api } from "../api/client";
import type { IngestResult } from "../api/types";

const stages: PipelineStage[] = [
  {
    id: "upload",
    label: "Upload PDF",
    description: "Select OEM manual",
    icon: Upload,
    detail: {
      what: "The PDF is loaded into memory and validated for structure and page count before processing starts.",
      input: "PDF File",
      output: "Byte Stream",
      tech: "Multipart upload → in-memory buffer",
    },
  },
  {
    id: "layout",
    label: "Layout Parse",
    description: "Document AI extraction",
    icon: FileSearch,
    detail: {
      what: "Document AI scans each page and identifies structural regions: headings, paragraphs, tables, lists, figures. Preserves the hierarchy instead of flattening it to plain text.",
      input: "Raw Pages",
      output: "Structured Blocks",
      tech: "Document AI Layout Parser v1.1",
    },
  },
  {
    id: "ocr",
    label: "OCR Pass",
    description: "Low-text page fallback",
    icon: ScanText,
    detail: {
      what: "Pages with little detected text get a second OCR pass. Catches scanned pages, text baked into images, and handwritten notes the layout parser missed.",
      input: "Image-heavy Pages",
      output: "Extracted Text",
      tech: "Document AI OCR + fallback heuristic",
    },
  },
  {
    id: "visual",
    label: "Visual Summary",
    description: "Gemini page images",
    icon: Eye,
    detail: {
      what: "Diagrams and figures are sent to Gemini as images. It writes text descriptions so visual content becomes searchable.",
      input: "Page Images",
      output: "Text Descriptions",
      tech: "Gemini 2.0 Flash multimodal",
    },
  },
  {
    id: "chunk",
    label: "Chunking",
    description: "Paragraphs / tables / figures",
    icon: Scissors,
    detail: {
      what: "The document gets split into chunks by paragraph, table, or figure. Splits follow heading boundaries so each chunk keeps its context.",
      input: "Full Document",
      output: "Semantic Chunks",
      tech: "Heading-aware recursive splitter",
    },
  },
  {
    id: "embed",
    label: "Embedding",
    description: "Vertex AI 768-dim",
    icon: Binary,
    detail: {
      what: "Each chunk becomes a 768-dimensional vector that captures its meaning. Similar content ends up close together in vector space.",
      input: "Text Chunks",
      output: "768-dim Vectors",
      tech: "Vertex AI text-embedding-005",
    },
  },
  {
    id: "upsert",
    label: "Pinecone Upsert",
    description: "oem_manuals index",
    icon: DatabaseZap,
    detail: {
      what: "Vectors get written to the oem_manuals namespace with metadata: document ID, page number, chunk type, manufacturer. Enables filtered search at query time.",
      input: "Vectors + Metadata",
      output: "Indexed Entries",
      tech: "Pinecone Serverless (us-east-1)",
    },
  },
];

export default function ManualIngest() {
  const [form, setForm] = useState({
    doc_id: "",
    manufacturer: "",
    machine_model: "",
    machine_family: "",
    manual_version: "",
  });
  const [pdfFile, setPdfFile] = useState<File | null>(null);
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
    if (!pdfFile && !form.doc_id) return;
    setRunning(true);
    setError(null);
    setResult(null);

    const simulateStages = async () => {
      for (let i = 0; i < stages.length - 1; i++) {
        setActiveStage(i);
        await new Promise((r) => setTimeout(r, 600));
      }
    };

    const stageAnimation = simulateStages();

    try {
      const metadata = {
        doc_id: form.doc_id || `manual_${form.machine_model}_${form.manual_version}`,
        manufacturer: form.manufacturer || "OEM",
        machine_model: form.machine_model,
        machine_family: form.machine_family || undefined,
        manual_version: form.manual_version,
        activate_version: true,
      };
      const res = pdfFile
        ? await api.ingestManualUpload(pdfFile, metadata)
        : await api.ingestManual({ ...metadata, pdf_path: undefined });
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
  }, [form, pdfFile]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-text-primary">OEM Manual Ingestion</h1>
        <p className="mt-1.5 text-sm text-text-secondary">
          Upload a PDF manual to parse, chunk, embed, and index into the OEM knowledge base.
        </p>
      </div>

      {/* Pipeline visualization */}
      <div className="rounded-2xl bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Ingestion Pipeline
          </h2>
          {running && <StatusBadge status="running" label="Processing..." />}
          {result && <StatusBadge status="done" label={`${result.chunk_count} chunks`} />}
          {error && <StatusBadge status="error" label="Failed" />}
        </div>
        <PipelineFlow
          stages={stages}
          activeIndex={activeStage}
          error={!!error}
          className="h-52"
        />
      </div>

      {/* Input form */}
      <div className="grid grid-cols-2 gap-8">
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-text-primary">PDF Document</h3>
          <FileDropzone accept=".pdf" onFile={setPdfFile} />
        </div>

        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-text-primary">Manual Metadata</h3>
          {[
            { key: "doc_id", label: "Document ID", placeholder: "kohler_kd27v12_om_33521029401" },
            { key: "manufacturer", label: "Manufacturer", placeholder: "Kohler" },
            { key: "machine_model", label: "Machine Model", placeholder: "KD27V12" },
            { key: "machine_family", label: "Machine Family", placeholder: "generator" },
            { key: "manual_version", label: "Manual Version", placeholder: "v7.1" },
          ].map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="mb-1 block text-[11px] font-medium text-text-muted">{label}</label>
              <input
                value={form[key as keyof typeof form]}
                onChange={updateField(key)}
                placeholder={placeholder}
                className="w-full rounded-xl border border-border bg-white px-3.5 py-2 font-mono text-sm text-text-primary shadow-sm placeholder:text-text-muted focus:border-accent-blue focus:outline-none focus:ring-2 focus:ring-accent-blue/20 transition-shadow"
              />
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={running || !form.machine_model || !form.manual_version}
        className="rounded-xl bg-accent-blue px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-accent-blue/90 hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {running ? "Processing..." : "Start Ingestion"}
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
            <h3 className="mb-3 text-sm font-semibold text-accent-green">Ingestion Complete</h3>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <Stat label="Corpus" value={result.corpus} />
              <Stat label="Namespace" value={result.namespace} />
              <Stat label="Chunks Created" value={String(result.chunk_count)} />
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
