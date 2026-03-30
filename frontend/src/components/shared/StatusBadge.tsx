import { motion } from "framer-motion";

export type StatusType = "pending" | "running" | "done" | "error";

const styles: Record<StatusType, string> = {
  pending: "bg-text-muted/10 text-text-muted",
  running: "bg-accent-blue/10 text-accent-blue",
  done: "bg-accent-green/10 text-accent-green",
  error: "bg-accent-red/10 text-accent-red",
};

export function StatusBadge({ status, label }: { status: StatusType; label?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${styles[status]}`}
    >
      {status === "running" && (
        <motion.span
          className="inline-block h-1.5 w-1.5 rounded-full bg-current"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1.2, repeat: Infinity }}
        />
      )}
      {label ?? status}
    </span>
  );
}
