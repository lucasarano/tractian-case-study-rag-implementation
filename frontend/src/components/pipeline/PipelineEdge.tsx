import { memo } from "react";
import { BaseEdge, getSmoothStepPath, type EdgeProps } from "@xyflow/react";

function PipelineEdgeInner(props: EdgeProps) {
  const { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data } = props;

  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 12,
  });

  const isActive = (data as Record<string, unknown>)?.active === true;

  return (
    <BaseEdge
      path={edgePath}
      style={{
        stroke: isActive ? "#007AFF" : "#d1d1d6",
        strokeWidth: isActive ? 2 : 1.5,
        transition: "stroke 0.4s, stroke-width 0.4s",
      }}
    />
  );
}

export const PipelineEdge = memo(PipelineEdgeInner);
