import { motion } from "framer-motion";
import { FileText, ScrollText } from "lucide-react";
import type { SupportingEvidence } from "../../api/types";

export function EvidenceCard({ evidence, index }: { evidence: SupportingEvidence; index: number }) {
  const isManual = evidence.source_type === "oem_manual";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      className={`rounded-2xl p-4 ${
        isManual
          ? "bg-accent-blue/5 border border-accent-blue/10"
          : "bg-accent-amber/5 border border-accent-amber/10"
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${
            isManual ? "bg-accent-blue/10" : "bg-accent-amber/10"
          }`}
        >
          {isManual ? (
            <FileText className="h-3.5 w-3.5 text-manual" />
          ) : (
            <ScrollText className="h-3.5 w-3.5 text-log" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`font-mono text-[10px] font-bold ${
                isManual ? "text-manual" : "text-log"
              }`}
            >
              {evidence.citation_id}
            </span>
            <span className="font-mono text-[10px] text-text-muted">{evidence.citation}</span>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{evidence.excerpt}</p>
        </div>
      </div>
    </motion.div>
  );
}
