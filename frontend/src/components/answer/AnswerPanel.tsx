import { motion } from "framer-motion";
import { Shield, Wrench, ArrowUpRight, MessageCircle } from "lucide-react";
import type { CopilotAnswer } from "../../api/types";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { SafetyBanner } from "./SafetyBanner";
import { CauseCard } from "./CauseCard";
import { CheckList } from "./CheckList";
import { EvidenceCard } from "./EvidenceCard";

const urgencyColors = {
  low: "bg-accent-green/10 text-accent-green",
  medium: "bg-accent-amber/10 text-accent-amber",
  high: "bg-accent-red/10 text-accent-red",
};

interface AnswerPanelProps {
  answer: CopilotAnswer;
  onFollowUpClick?: (question: string) => void;
}

export function AnswerPanel({ answer, onFollowUpClick }: AnswerPanelProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-4"
    >
      {/* Primary answer */}
      <div className="rounded-2xl border border-border bg-white p-5 shadow-sm">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.24em] text-text-muted">
          Answer
        </p>
        <h3 className="text-base font-semibold leading-7 text-text-primary">
          {answer.issue_summary}
        </h3>
      </div>

      {/* Follow-up question */}
      {answer.follow_up_question && (
        <button
          type="button"
          onClick={() => onFollowUpClick?.(answer.follow_up_question!)}
          className="group w-full rounded-2xl border border-accent-purple/15 bg-accent-purple/5 p-4 text-left transition-colors hover:border-accent-purple/30 hover:bg-accent-purple/10"
        >
          <div className="flex items-center gap-2">
            <MessageCircle className="h-3.5 w-3.5 text-accent-purple" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-accent-purple">
              Suggested follow-up
            </span>
          </div>
          <p className="mt-2 text-sm font-medium text-text-primary group-hover:text-accent-purple transition-colors">
            {answer.follow_up_question}
          </p>
          <p className="mt-1 text-[11px] text-text-muted">
            Click to use as your next question
          </p>
        </button>
      )}

      {/* Recommended checks */}
      <CheckList checks={answer.recommended_checks} />

      {/* Suspected causes */}
      {answer.suspected_causes.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
            Suspected Causes
          </h4>
          <div className="space-y-2">
            {answer.suspected_causes.map((cause, i) => (
              <CauseCard key={i} cause={cause} index={i} />
            ))}
          </div>
        </div>
      )}

      {/* Required tools */}
      {answer.required_tools.length > 0 && (
        <div>
          <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-muted">
            <Wrench className="h-3.5 w-3.5" />
            Required Tools
          </h4>
          <div className="flex flex-wrap gap-2">
            {answer.required_tools.map((tool) => (
              <span
                key={tool}
                className="rounded-full bg-accent-purple/8 px-3 py-1 text-[11px] font-medium text-accent-purple"
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Supporting evidence / citations */}
      {answer.supporting_evidence.length > 0 && (
        <div>
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
            Citations
          </h4>
          <div className="space-y-2">
            {answer.supporting_evidence.map((ev, i) => (
              <EvidenceCard key={ev.citation_id} evidence={ev} index={i} />
            ))}
          </div>
        </div>
      )}

      <SafetyBanner warnings={answer.safety_warnings} />

      {/* Escalation */}
      {answer.escalate_if.length > 0 && (
        <div className="rounded-2xl border border-accent-amber/20 bg-accent-amber/5 p-4">
          <h4 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase text-accent-amber">
            <ArrowUpRight className="h-3.5 w-3.5" />
            Escalate If
          </h4>
          <ul className="space-y-0.5">
            {answer.escalate_if.map((e, i) => (
              <li key={i} className="text-xs text-text-secondary">
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-2xl border border-border bg-white/80 p-4 shadow-sm">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Confidence
            </p>
            <ConfidenceMeter value={answer.confidence} />
          </div>
          <div className="text-right">
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Urgency
            </p>
            <span
              className={`inline-flex rounded-full px-3 py-1 text-[11px] font-bold uppercase ${urgencyColors[answer.urgency]}`}
            >
              {answer.urgency}
            </span>
          </div>
        </div>
      </div>

      {/* High-urgency shield */}
      {answer.urgency === "high" && (
        <div className="flex items-center gap-2.5 rounded-2xl border border-accent-red/20 bg-accent-red/5 px-4 py-3">
          <Shield className="h-4 w-4 text-accent-red" />
          <span className="text-xs font-medium text-accent-red">
            High urgency — consider immediate escalation
          </span>
        </div>
      )}
    </motion.div>
  );
}
