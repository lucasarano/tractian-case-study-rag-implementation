import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { motion } from "framer-motion";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  type LucideIcon,
} from "lucide-react";

export type PipelineStatus = "pending" | "running" | "done" | "error";

export interface PipelineNodeData {
  label: string;
  description?: string;
  status: PipelineStatus;
  icon?: LucideIcon;
  [key: string]: unknown;
}

const statusConfig: Record<
  PipelineStatus,
  { ring: string; shadow: string; Icon: LucideIcon; iconColor: string }
> = {
  pending: {
    ring: "",
    shadow: "shadow-sm",
    Icon: Circle,
    iconColor: "text-text-muted",
  },
  running: {
    ring: "ring-2 ring-accent-blue/30",
    shadow: "shadow-md",
    Icon: Loader2,
    iconColor: "text-accent-blue",
  },
  done: {
    ring: "",
    shadow: "shadow-sm",
    Icon: CheckCircle2,
    iconColor: "text-accent-green",
  },
  error: {
    ring: "ring-2 ring-accent-red/30",
    shadow: "shadow-sm",
    Icon: XCircle,
    iconColor: "text-accent-red",
  },
};

function PipelineNodeInner({ data }: NodeProps) {
  const nodeData = data as unknown as PipelineNodeData;
  const { label, description, status, icon: CustomIcon } = nodeData;
  const config = statusConfig[status];
  const DisplayIcon = CustomIcon ?? config.Icon;

  return (
    <>
      <Handle type="target" position={Position.Left} className="!bg-border !border-0 !w-2 !h-2" />
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        whileHover={{ scale: 1.03 }}
        className={`w-56 cursor-pointer rounded-2xl bg-white px-5 py-5 transition-shadow hover:shadow-md ${config.ring} ${config.shadow}`}
      >
        <div className="flex items-start gap-3.5">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-bg-secondary">
            {status === "running" ? (
              <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                <Loader2 className={`h-[18px] w-[18px] ${config.iconColor}`} />
              </motion.div>
            ) : (
              <DisplayIcon className={`h-[18px] w-[18px] ${config.iconColor}`} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-text-primary">{label}</p>
            {description && (
              <p className="mt-1 text-xs leading-snug text-text-muted">{description}</p>
            )}
          </div>
        </div>
      </motion.div>
      <Handle type="source" position={Position.Right} className="!bg-border !border-0 !w-2 !h-2" />
    </>
  );
}

export const PipelineNode = memo(PipelineNodeInner);
