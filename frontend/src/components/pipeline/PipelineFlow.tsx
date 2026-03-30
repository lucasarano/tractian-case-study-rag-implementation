import { useState, useMemo, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  ReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  Background,
  BackgroundVariant,
} from "@xyflow/react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ArrowRight, Loader2 } from "lucide-react";
import { PipelineNode } from "./PipelineNode";
import { PipelineEdge } from "./PipelineEdge";
import type { PipelineStatus } from "./PipelineNode";
import type { LucideIcon } from "lucide-react";

/* ── types ── */

export interface StageDetail {
  what: string;
  input: string;
  output: string;
  tech: string;
}

export interface PipelineStage {
  id: string;
  label: string;
  description?: string;
  icon?: LucideIcon;
  detail?: StageDetail;
}

interface Props {
  stages: PipelineStage[];
  activeIndex: number;
  error?: boolean;
  className?: string;
}

interface SelectedStage {
  stage: PipelineStage;
  status: PipelineStatus;
  stageIndex: number;
  totalStages: number;
  originX: number;
  originY: number;
}

/* ── helpers ── */

const nodeTypes: NodeTypes = { pipeline: PipelineNode };
const edgeTypes: EdgeTypes = { pipeline: PipelineEdge };

function statusForIndex(i: number, activeIndex: number, error?: boolean): PipelineStatus {
  if (i < activeIndex) return "done";
  if (i === activeIndex) return error ? "error" : "running";
  return "pending";
}

const statusLabel: Record<PipelineStatus, string> = {
  pending: "Queued",
  running: "In progress",
  done: "Complete",
  error: "Failed",
};

const statusColor: Record<
  PipelineStatus,
  { bar: string; pill: string; pillBg: string }
> = {
  pending: { bar: "bg-text-muted/20", pill: "text-text-muted", pillBg: "bg-bg-secondary" },
  running: { bar: "bg-accent-blue", pill: "text-accent-blue", pillBg: "bg-accent-blue/10" },
  done: { bar: "bg-accent-green", pill: "text-accent-green", pillBg: "bg-accent-green/10" },
  error: { bar: "bg-accent-red", pill: "text-accent-red", pillBg: "bg-accent-red/10" },
};

/* ── stage detail popup ── */

function StagePopup({
  stage,
  status,
  stageIndex,
  totalStages,
  originX,
  originY,
  onClose,
}: SelectedStage & { onClose: () => void }) {
  const colors = statusColor[status];
  const Icon = stage.icon;

  const centerX = window.innerWidth / 2;
  const centerY = window.innerHeight / 2;
  const offsetX = originX - centerX;
  const offsetY = originY - centerY;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const bar =
    status === "running" ? (
      <motion.div
        className={`h-1 ${colors.bar}`}
        animate={{ opacity: [1, 0.5, 1] }}
        transition={{ duration: 1.5, repeat: Infinity }}
      />
    ) : (
      <div className={`h-1 ${colors.bar}`} />
    );

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="absolute inset-0 bg-black/15 backdrop-blur-[2px]"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />

      <motion.div
        className="relative z-10 w-[400px] overflow-hidden rounded-2xl border border-border bg-white shadow-2xl"
        initial={{ opacity: 0, scale: 0.35, x: offsetX, y: offsetY }}
        animate={{ opacity: 1, scale: 1, x: 0, y: 0 }}
        exit={{ opacity: 0, scale: 0.35, x: offsetX, y: offsetY }}
        transition={{ type: "spring", damping: 28, stiffness: 320 }}
      >
        {bar}

        <div className="p-5">
          {/* header */}
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              {Icon && (
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-bg-secondary">
                  {status === "running" ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
                    >
                      <Loader2 className="h-5 w-5 text-accent-blue" />
                    </motion.div>
                  ) : (
                    <Icon className="h-5 w-5 text-text-secondary" />
                  )}
                </div>
              )}
              <div>
                <h3 className="text-base font-bold text-text-primary">{stage.label}</h3>
                <div className="mt-0.5 flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${colors.pill} ${colors.pillBg}`}
                  >
                    {statusLabel[status]}
                  </span>
                  <span className="text-[10px] text-text-muted/40">
                    Step {stageIndex + 1} of {totalStages}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-secondary"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* explanation */}
          {stage.detail && (
            <>
              <p className="mt-4 text-[13px] leading-relaxed text-text-secondary">
                {stage.detail.what}
              </p>

              {/* input → output */}
              <div className="mt-4 flex items-stretch gap-2.5">
                <div className="flex-1 rounded-xl bg-bg-secondary px-3.5 py-2.5">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-text-muted/50">
                    In
                  </p>
                  <p className="mt-0.5 text-xs font-semibold text-text-primary">
                    {stage.detail.input}
                  </p>
                </div>
                <div className="flex items-center text-text-muted/30">
                  {status === "running" ? (
                    <motion.div
                      animate={{ x: [0, 4, 0] }}
                      transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
                    >
                      <ArrowRight className="h-4 w-4" />
                    </motion.div>
                  ) : (
                    <ArrowRight className="h-4 w-4" />
                  )}
                </div>
                <div className="flex-1 rounded-xl bg-bg-secondary px-3.5 py-2.5">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-text-muted/50">
                    Out
                  </p>
                  <p className="mt-0.5 text-xs font-semibold text-text-primary">
                    {stage.detail.output}
                  </p>
                </div>
              </div>

              {/* tech note */}
              <div className="mt-3.5 flex items-center gap-2">
                <div className="h-px flex-1 bg-border/50" />
                <p className="font-mono text-[10px] text-text-muted/40">
                  {stage.detail.tech}
                </p>
                <div className="h-px flex-1 bg-border/50" />
              </div>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ── pipeline flow ── */

export function PipelineFlow({ stages, activeIndex, error, className }: Props) {
  const [selected, setSelected] = useState<SelectedStage | null>(null);

  const { nodes, edges } = useMemo(() => {
    const n: Node[] = stages.map((stage, i) => ({
      id: stage.id,
      type: "pipeline",
      position: { x: i * 275, y: 0 },
      data: {
        label: stage.label,
        description: stage.description,
        status: statusForIndex(i, activeIndex, error),
        icon: stage.icon,
      },
      draggable: false,
    }));

    const e: Edge[] = stages.slice(1).map((stage, i) => ({
      id: `e-${stages[i].id}-${stage.id}`,
      source: stages[i].id,
      target: stage.id,
      type: "pipeline",
      data: { active: i < activeIndex },
    }));

    return { nodes: n, edges: e };
  }, [stages, activeIndex, error]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const idx = stages.findIndex((s) => s.id === node.id);
      if (idx === -1) return;
      setSelected({
        stage: stages[idx],
        status: statusForIndex(idx, activeIndex, error),
        stageIndex: idx,
        totalStages: stages.length,
        originX: _event.clientX,
        originY: _event.clientY,
      });
    },
    [stages, activeIndex, error],
  );

  return (
    <div className={`h-52 w-full ${className ?? ""}`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#e5e5ea" />
      </ReactFlow>

      {createPortal(
        <AnimatePresence>
          {selected && (
            <StagePopup {...selected} onClose={() => setSelected(null)} />
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
}
