import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  History,
  ChevronRight,
  RefreshCw,
  Loader2,
  AlertCircle,
  ClipboardList,
  Lightbulb,
  ListChecks,
} from "lucide-react";
import type { SessionRecord } from "../api/types";
import { api } from "../api/client";

export default function Sessions() {
  const [sessionId, setSessionId] = useState("");
  const [session, setSession] = useState<SessionRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await api.createSession({
        machine_id: "GEN-KD27-003",
        site_id: "plant-north",
        machine_model: "KD27V12",
        machine_family: "generator",
        criticality: "high",
      });
      setSession(s);
      setSessionId(s.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create session");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-text-primary">Sessions</h1>
        <p className="mt-1.5 text-sm text-text-secondary">
          View and inspect copilot troubleshooting sessions. Sessions track hypotheses, completed
          checks, measurements, and next actions across conversations.
        </p>
      </div>

      {/* Create demo session */}
      <div className="flex gap-4">
        <button
          onClick={createDemo}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl bg-accent-blue px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-accent-blue/90 hover:shadow-md disabled:opacity-40"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Create Demo Session
        </button>
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <History className="h-4 w-4" />
          Sessions are created automatically when you ask questions on the Troubleshoot page
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 rounded-2xl border border-accent-red/20 bg-accent-red/5 px-4 py-3">
          <AlertCircle className="h-4 w-4 text-accent-red" />
          <p className="text-xs text-accent-red">{error}</p>
        </div>
      )}

      {/* Session detail */}
      <AnimatePresence>
        {session && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-5"
          >
            {/* Header */}
            <div className="rounded-2xl bg-white p-5 shadow-sm">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-blue/10">
                  <History className="h-4 w-4 text-accent-blue" />
                </div>
                <span className="text-sm font-semibold text-text-primary">Session Detail</span>
              </div>
              <div className="grid grid-cols-4 gap-5">
                <Field label="Session ID" value={session.session_id} mono />
                <Field label="Tenant" value={session.tenant_id} mono />
                <Field label="User" value={session.user_id} mono />
                <Field label="Machine" value={session.machine_id} mono />
              </div>
              <div className="mt-4 grid grid-cols-4 gap-5">
                <Field label="Opened" value={new Date(session.opened_at).toLocaleString()} />
                <Field label="Updated" value={new Date(session.updated_at).toLocaleString()} />
                <Field label="Work Order" value={session.work_order_id ?? "\u2014"} mono />
                <Field
                  label="Context Summary"
                  value={session.last_context_summary ?? "\u2014"}
                />
              </div>
            </div>

            {/* State */}
            <div className="grid grid-cols-3 gap-5">
              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <div className="flex items-center gap-1.5 mb-3">
                  <ClipboardList className="h-3.5 w-3.5 text-accent-purple" />
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    Issue Summary
                  </h4>
                </div>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {session.state.issue_summary || "Not set yet"}
                </p>
              </div>

              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <div className="flex items-center gap-1.5 mb-3">
                  <Lightbulb className="h-3.5 w-3.5 text-accent-amber" />
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    Hypotheses
                  </h4>
                </div>
                {session.state.hypotheses.length > 0 ? (
                  <div className="space-y-2">
                    {session.state.hypotheses.map((h, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-xl bg-bg-secondary px-3 py-2"
                      >
                        <span className="text-xs text-text-secondary">{h.cause}</span>
                        <span className="font-mono text-[10px] font-semibold text-accent-amber">
                          {Math.round(h.confidence * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-text-muted">No hypotheses yet</p>
                )}
              </div>

              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <div className="flex items-center gap-1.5 mb-3">
                  <ListChecks className="h-3.5 w-3.5 text-accent-green" />
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    Next Actions
                  </h4>
                </div>
                {session.state.next_actions.length > 0 ? (
                  <ul className="space-y-1.5">
                    {session.state.next_actions.map((a, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-accent-green" />
                        <span className="text-xs text-text-secondary">{a}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-text-muted">No actions yet</p>
                )}
              </div>
            </div>

            {/* Checks and measurements */}
            <div className="grid grid-cols-2 gap-5">
              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <h4 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                  Completed Checks
                </h4>
                {session.state.checks_completed.length > 0 ? (
                  <div className="space-y-1.5">
                    {session.state.checks_completed.map((c, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between rounded-xl bg-bg-secondary px-3 py-2"
                      >
                        <span className="text-xs text-text-secondary">{c.check}</span>
                        <span
                          className={`text-[10px] font-medium ${
                            c.status === "completed"
                              ? "text-accent-green"
                              : c.status === "skipped"
                                ? "text-text-muted"
                                : "text-accent-amber"
                          }`}
                        >
                          {c.status}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-text-muted">No checks recorded</p>
                )}
              </div>

              <div className="rounded-2xl bg-white p-5 shadow-sm">
                <h4 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                  Measurements
                </h4>
                {Object.keys(session.state.measurements).length > 0 ? (
                  <pre className="font-mono text-xs text-text-secondary">
                    {JSON.stringify(session.state.measurements, null, 2)}
                  </pre>
                ) : (
                  <p className="text-xs text-text-muted">No measurements recorded</p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{label}</p>
      <p className={`mt-0.5 text-sm text-text-primary ${mono ? "font-mono" : ""}`}>
        {value}
      </p>
    </div>
  );
}
