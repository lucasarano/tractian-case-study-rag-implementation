import { motion } from "framer-motion";
import { ClipboardCheck, AlertOctagon, BookOpen } from "lucide-react";
import type { RecommendedCheck } from "../../api/types";

export function CheckList({ checks }: { checks: RecommendedCheck[] }) {
  if (checks.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-muted">
        <ClipboardCheck className="h-3.5 w-3.5" />
        Recommended Checks
      </h4>
      <div className="space-y-2">
        {checks.map((check, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            className="rounded-2xl bg-white p-4 shadow-sm"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-blue/10 text-[11px] font-bold text-accent-blue">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-text-primary">{check.step}</p>
                <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                  <span className="text-accent-green">
                    <span className="font-semibold">Expected:</span> {check.expected}
                  </span>
                  <span className="flex items-center gap-1 text-accent-red">
                    <AlertOctagon className="h-3 w-3" />
                    <span className="font-semibold">Stop if:</span> {check.stop_if}
                  </span>
                </div>
                <div className="mt-2 flex gap-1.5">
                  {check.citations.map((c) => (
                    <span
                      key={c}
                      className="inline-flex items-center gap-0.5 rounded-lg bg-accent-blue/8 px-2 py-0.5 font-mono text-[10px] text-accent-blue"
                    >
                      <BookOpen className="h-2.5 w-2.5" />
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
