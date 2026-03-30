import { useState, useCallback, useEffect, memo } from "react";
import { useNavigate } from "react-router-dom";
import {
  ReactFlow,
  Handle,
  Position,
  Background,
  BackgroundVariant,
  type NodeTypes,
  type NodeProps,
  type Node,
} from "@xyflow/react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Monitor,
  Server,
  FileText,
  ScrollText,
  GitBranch,
  Cloud,
  Cpu,
  BarChart3,
  Database as DbIcon,
  Layers,
  X,
  ExternalLink,
} from "lucide-react";
import { archNodes, archEdges } from "../lib/flows";

/* ── category config ── */

const categoryConfig: Record<
  string,
  { color: string; bg: string; border: string; Icon: typeof Monitor }
> = {
  frontend: { color: "text-accent-cyan", bg: "bg-accent-cyan/8", border: "border-accent-cyan/20", Icon: Monitor },
  api: { color: "text-accent-blue", bg: "bg-accent-blue/8", border: "border-accent-blue/20", Icon: Server },
  ingest: { color: "text-accent-green", bg: "bg-accent-green/8", border: "border-accent-green/20", Icon: FileText },
  graph: { color: "text-accent-purple", bg: "bg-accent-purple/8", border: "border-accent-purple/20", Icon: GitBranch },
  gcp: { color: "text-accent-amber", bg: "bg-accent-amber/8", border: "border-accent-amber/20", Icon: Cloud },
  vector: { color: "text-accent-green", bg: "bg-accent-green/8", border: "border-accent-green/20", Icon: Layers },
  infra: { color: "text-text-secondary", bg: "bg-bg-tertiary", border: "border-border", Icon: DbIcon },
};

const iconOverrides: Record<string, typeof Monitor> = {
  log_ingest: ScrollText,
  vertexai: Cpu,
  ranking: BarChart3,
};

/* ── types ── */

interface NodeDetail {
  role: string;
  importance: string;
  whyChosen: string;
}

interface ArchNodeData {
  label: string;
  category: string;
  description: string;
  summary?: string;
  detail?: NodeDetail;
  link?: string;
}

interface HoveredNode {
  data: ArchNodeData;
  x: number;
  y: number;
}

interface SelectedNode {
  id: string;
  data: ArchNodeData;
  originX: number;
  originY: number;
}

/* ── architecture node ── */

function ArchNodeInner({ id, data }: NodeProps) {
  const d = data as unknown as ArchNodeData;
  const config = categoryConfig[d.category] ?? categoryConfig.infra;
  const Icon = iconOverrides[id] ?? config.Icon;

  return (
    <>
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0" />
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        whileHover={{ scale: 1.04 }}
        className={`w-44 cursor-pointer rounded-2xl border bg-white px-4 py-3 shadow-sm transition-shadow hover:shadow-md ${config.border}`}
      >
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${config.color}`} />
          <span className={`text-xs font-semibold ${config.color}`}>{d.label}</span>
        </div>
        <p className="mt-0.5 text-[10px] text-text-muted">{d.description}</p>
      </motion.div>
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0" />
    </>
  );
}

const ArchNode = memo(ArchNodeInner);
const nodeTypes: NodeTypes = { archNode: ArchNode };

const defaultEdgeOptions = {
  style: { stroke: "#d1d1d6", strokeWidth: 1.5 },
  type: "smoothstep" as const,
};

/* ── detail popup ── */

function DetailSection({ title, content }: { title: string; content: string }) {
  return (
    <div>
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {title}
      </h4>
      <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{content}</p>
    </div>
  );
}

function DetailPopup({
  id,
  data,
  originX,
  originY,
  onClose,
}: SelectedNode & { onClose: () => void }) {
  const navigate = useNavigate();
  const config = categoryConfig[data.category] ?? categoryConfig.infra;
  const Icon = iconOverrides[id] ?? config.Icon;

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

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="absolute inset-0 bg-black/20 backdrop-blur-[2px]"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />

      <motion.div
        className="relative z-10 w-[480px] max-h-[80vh] overflow-y-auto rounded-2xl border border-border bg-white p-6 shadow-2xl"
        initial={{ opacity: 0, scale: 0.35, x: offsetX, y: offsetY }}
        animate={{ opacity: 1, scale: 1, x: 0, y: 0 }}
        exit={{ opacity: 0, scale: 0.35, x: offsetX, y: offsetY }}
        transition={{ type: "spring", damping: 28, stiffness: 320 }}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`rounded-xl ${config.bg} p-2.5`}>
              <Icon className={`h-5 w-5 ${config.color}`} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-text-primary">{data.label}</h3>
              <p className="text-xs text-text-muted">{data.description}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-secondary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {data.detail && (
          <div className="mt-5 space-y-4">
            <DetailSection title="Role in the Pipeline" content={data.detail.role} />
            <DetailSection title="Why It Matters" content={data.detail.importance} />
            <DetailSection title="Why It Was Chosen" content={data.detail.whyChosen} />
          </div>
        )}

        {data.link && (
          <button
            onClick={() => {
              navigate(data.link!);
              onClose();
            }}
            className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-accent-blue/10 py-2.5 text-sm font-medium text-accent-blue transition-colors hover:bg-accent-blue/15"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {data.link === "/rag" ? "Open RAG Functionality" : `Navigate to ${data.label}`}
          </button>
        )}
      </motion.div>
    </motion.div>
  );
}

/* ── dashboard ── */

export default function Dashboard() {
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [hovered, setHovered] = useState<HoveredNode | null>(null);

  const handleNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setHovered(null);
    setSelected({
      id: node.id,
      data: node.data as unknown as ArchNodeData,
      originX: _event.clientX,
      originY: _event.clientY,
    });
  }, []);

  const handleNodeMouseEnter = useCallback(
    (event: React.MouseEvent, node: Node) => {
      if (selected) return;
      const nodeEl = (event.target as HTMLElement).closest(
        ".react-flow__node",
      ) as HTMLElement | null;
      if (!nodeEl) return;
      const rect = nodeEl.getBoundingClientRect();
      setHovered({
        data: node.data as unknown as ArchNodeData,
        x: rect.left + rect.width / 2,
        y: rect.bottom + 8,
      });
    },
    [selected],
  );

  const handleNodeMouseLeave = useCallback(() => {
    setHovered(null);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-text-primary">
          System Architecture
        </h1>
        <p className="mt-1.5 text-sm text-text-secondary">
          Interactive overview of the Maintenance Copilot pipeline. Use this view to inspect the
          end-to-end architecture, then jump into the RAG workspace to explore the loaded manual
          subset and query the system against it.
        </p>
      </div>

      <div className="h-[520px] overflow-hidden rounded-2xl bg-white shadow-sm">
        <ReactFlow
          nodes={archNodes}
          edges={archEdges}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          onNodeClick={handleNodeClick}
          onNodeMouseEnter={handleNodeMouseEnter}
          onNodeMouseLeave={handleNodeMouseLeave}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e5ea" />
        </ReactFlow>
      </div>

      <div className="flex flex-wrap gap-5">
        {Object.entries(categoryConfig).map(([key, { color, Icon }]) => (
          <div key={key} className="flex items-center gap-1.5">
            <Icon className={`h-3.5 w-3.5 ${color}`} />
            <span className="text-[11px] capitalize text-text-muted">{key}</span>
          </div>
        ))}
      </div>

      {/* hover tooltip — fixed outside ReactFlow so it isn't clipped by overflow-hidden */}
      <AnimatePresence>
        {hovered?.data.summary && (
          <motion.div
            key="tooltip"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            style={{ left: hovered.x, top: hovered.y, x: "-50%" }}
            className="pointer-events-none fixed z-50 w-64 rounded-xl border border-border bg-white/95 px-4 py-3 shadow-lg backdrop-blur-sm"
          >
            <p className="text-[11px] leading-relaxed text-text-secondary">
              {hovered.data.summary}
            </p>
            <p className="mt-2 text-[10px] italic text-text-muted/40">Click to learn more</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* detail popup */}
      <AnimatePresence>
        {selected && (
          <DetailPopup
            key="detail"
            id={selected.id}
            data={selected.data}
            originX={selected.originX}
            originY={selected.originY}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
