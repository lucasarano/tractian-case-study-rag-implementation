import { motion } from "framer-motion";
import type { SuspectedCause } from "../../api/types";

function colorForConfidence(c: number) {
  if (c >= 0.75) return "#34C759";
  if (c >= 0.5) return "#FF9500";
  return "#FF3B30";
}

export function CauseCard({ cause, index }: { cause: SuspectedCause; index: number }) {
  const pct = Math.round(cause.confidence * 100);
  const color = colorForConfidence(cause.confidence);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      className="rounded-2xl bg-white p-4 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-text-primary">{cause.cause}</p>
          <p className="mt-1 text-xs text-text-secondary leading-relaxed">{cause.why}</p>
        </div>
        <div className="flex flex-col items-end">
          <span className="font-mono text-lg font-bold" style={{ color }}>
            {pct}%
          </span>
          <div className="mt-1 h-1.5 w-14 overflow-hidden rounded-full bg-bg-tertiary">
            <motion.div
              className="h-full rounded-full"
              style={{ backgroundColor: color }}
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.6, delay: index * 0.1 }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
