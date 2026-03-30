import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Loader2,
  Database,
  Search,
  PenTool,
  Save,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  MessageSquareText,
} from "lucide-react";
import { AnswerPanel } from "../components/answer/AnswerPanel";
import { api } from "../api/client";
import type { AnswerEnvelope } from "../api/types";

type Stage = "idle" | "load_context" | "retrieve" | "compose" | "persist" | "done";

const STAGE_ORDER: Stage[] = ["load_context", "retrieve", "compose", "persist", "done"];

function stageStatus(current: Stage, check: Stage) {
  const ci = STAGE_ORDER.indexOf(current);
  const ti = STAGE_ORDER.indexOf(check);
  if (ci < 0 || ti < 0) return "pending";
  if (ti < ci) return "done";
  if (ti === ci) return "active";
  return "pending";
}

const PDF_TOTAL_PAGES = 50;
const PDF_SUBSET_URL = "/v1/manuals/loaded-subset-pdf";

const FIXED_CONTEXT = {
  machine_id: "GEN-KD27-003",
  site_id: "plant-north",
  machine_model: "KD27V12",
  machine_family: "generator",
  criticality: "high" as const,
};

export default function RagFunctionality() {
  const [message, setMessage] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [result, setResult] = useState<AnswerEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pdfPage, setPdfPage] = useState(1);

  const pdfUrl = `${PDF_SUBSET_URL}#page=${pdfPage}&zoom=page-width&toolbar=1`;

  const goToPdfPage = useCallback(
    (p: number) => setPdfPage(Math.min(PDF_TOTAL_PAGES, Math.max(1, p))),
    [],
  );

  const fillFollowUp = useCallback((q: string) => setMessage(q), []);

  const handleSubmit = useCallback(async () => {
    if (!message.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

    try {
      setStage("load_context");
      await wait(800);

      const promise = api.answer({
        message,
        ...FIXED_CONTEXT,
        session_id: sessionId || undefined,
      });

      setStage("retrieve");
      await wait(700);
      setStage("compose");
      await wait(600);
      setStage("persist");

      const res = await promise;
      await wait(400);
      setStage("done");
      setResult(res);
      setSessionId(res.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setStage("idle");
    } finally {
      setLoading(false);
    }
  }, [message, sessionId]);

  const PILLS = [
    { id: "load_context" as const, label: "Context", Icon: Database },
    { id: "retrieve" as const, label: "Retrieve", Icon: Search },
    { id: "compose" as const, label: "Compose", Icon: PenTool },
    { id: "persist" as const, label: "Persist", Icon: Save },
  ];

  return (
    <div className="space-y-6">
      {/* ── Question input ── */}
      <section className="rounded-3xl border border-border bg-white shadow-sm">
        <div className="px-6 py-6 sm:px-8">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight text-text-primary">
              Ask the Manual
            </h1>
            <span className="rounded-full bg-accent-blue/10 px-2.5 py-0.5 text-[11px] font-semibold text-accent-blue">
              First 50 pages
            </span>
          </div>
          <p className="mt-1 text-sm text-text-secondary">
            Kohler KD27V12 &mdash; retrieval-augmented answers from the first 50 pages of the
            service manual.
          </p>

          <div className="mt-5 flex gap-3">
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="e.g. Low oil pressure at 2.0 bar under load — what should I check?"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !loading) void handleSubmit();
              }}
              className="flex-1 rounded-2xl border border-border bg-bg-secondary px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-purple focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent-purple/20 transition-all"
            />
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={loading || !message.trim()}
              className="inline-flex items-center gap-2 rounded-2xl bg-accent-purple px-5 py-3 text-sm font-semibold text-white shadow-sm transition-all hover:bg-accent-purple/90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Ask
            </button>
          </div>

          {stage !== "idle" && (
            <div className="mt-4 flex flex-wrap gap-2">
              {PILLS.map(({ id, label, Icon }) => {
                const s = stageStatus(stage, id);
                return (
                  <div
                    key={id}
                    className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[11px] font-medium transition-colors ${
                      s === "active"
                        ? "bg-accent-purple/10 text-accent-purple"
                        : s === "done"
                          ? "bg-accent-green/10 text-accent-green"
                          : "bg-bg-tertiary text-text-muted"
                    }`}
                  >
                    {s === "active" ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Icon className="h-3 w-3" />
                    )}
                    {label}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* ── Answer + PDF ── */}
      <div className="grid gap-6 xl:grid-cols-[1fr_minmax(360px,0.85fr)]">
        {/* Left: answer area */}
        <div className="min-w-0">
          <AnimatePresence mode="wait">
            {result ? (
              <motion.div
                key="answer"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <AnswerPanel answer={result.answer} onFollowUpClick={fillFollowUp} />
              </motion.div>
            ) : error ? (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="rounded-2xl border border-accent-red/20 bg-accent-red/5 p-5"
              >
                <h3 className="mb-1 text-sm font-semibold text-accent-red">Error</h3>
                <p className="font-mono text-xs text-accent-red/80">{error}</p>
              </motion.div>
            ) : loading ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-white/60 py-24"
              >
                <Loader2 className="h-6 w-6 animate-spin text-accent-purple" />
                <p className="mt-3 text-sm text-text-muted">Processing your question…</p>
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-white/60 py-24"
              >
                <MessageSquareText className="h-6 w-6 text-text-muted" />
                <p className="mt-3 text-sm text-text-muted">
                  Ask a question to see the answer here.
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right: PDF viewer */}
        <section className="rounded-3xl border border-border bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-accent-blue" />
              <h2 className="text-sm font-semibold text-text-primary">Manual PDF</h2>
              <span className="text-xs text-text-muted">
                {pdfPage}/{PDF_TOTAL_PAGES}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => goToPdfPage(pdfPage - 1)}
                disabled={pdfPage === 1}
                className="rounded-lg border border-border p-1.5 text-text-primary transition-colors hover:bg-bg-secondary disabled:opacity-30"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => goToPdfPage(pdfPage + 1)}
                disabled={pdfPage === PDF_TOTAL_PAGES}
                className="rounded-lg border border-border p-1.5 text-text-primary transition-colors hover:bg-bg-secondary disabled:opacity-30"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
              <a
                href={pdfUrl}
                target="_blank"
                rel="noreferrer"
                className="ml-1 rounded-lg border border-border p-1.5 text-text-primary transition-colors hover:bg-bg-secondary"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>

          <div className="mt-3 overflow-hidden rounded-2xl border border-border bg-bg-secondary shadow-inner">
            <iframe
              src={pdfUrl}
              title="Manual PDF viewer"
              className="h-[600px] w-full bg-white lg:h-[720px]"
            />
          </div>
        </section>
      </div>
    </div>
  );
}
