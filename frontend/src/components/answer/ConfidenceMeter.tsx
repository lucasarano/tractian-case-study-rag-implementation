import { motion } from "framer-motion";

function colorForConfidence(c: number) {
  if (c >= 0.75) return "#34C759";
  if (c >= 0.5) return "#FF9500";
  return "#FF3B30";
}

export function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = colorForConfidence(value);

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg-tertiary">
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
      <span className="font-mono text-xs font-semibold" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}
