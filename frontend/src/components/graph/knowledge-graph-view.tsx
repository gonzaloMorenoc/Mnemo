"use client";

import { Background, Controls, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useState } from "react";

import type { Graph } from "@/lib/api/types";
import { toFlow } from "./graph-layout";

// ─── types ───────────────────────────────────────────────────────────────────

interface Props {
  graph: Graph;
  onNodeClick?: (id: string) => void;
}

// ─── component ───────────────────────────────────────────────────────────────

/**
 * KnowledgeGraphView renders a domain Graph using react-flow.
 *
 * Node colours by type:
 *  - knowledge → blue  (CSS class `node-knowledge`)
 *  - defect    → red   (CSS class `node-defect`)
 *  - domain    → grey  (CSS class `node-domain`)
 *
 * Clicking a node highlights it and its direct neighbours; all other nodes are
 * dimmed.  A second click on the same node deselects it.
 */
export function KnowledgeGraphView({ graph, onNodeClick }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (graph.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        sin datos
      </div>
    );
  }

  // Compute the set of neighbour ids for the currently selected node
  const neighbourIds = selectedId
    ? new Set(
        graph.edges
          .filter((e) => e.source === selectedId || e.target === selectedId)
          .flatMap((e) => [e.source, e.target])
          .filter((id) => id !== selectedId),
      )
    : new Set<string>();

  const { nodes: rawNodes, edges } = toFlow(graph);

  // Apply highlight/dim styles when a node is selected
  const nodes = rawNodes.map((node) => {
    if (!selectedId) return node;

    const isSelected = node.id === selectedId;
    const isNeighbour = neighbourIds.has(node.id);
    const dimmed = !isSelected && !isNeighbour;

    return {
      ...node,
      className: [node.className, isSelected ? "node-selected" : "", dimmed ? "node-dimmed" : ""]
        .filter(Boolean)
        .join(" "),
    };
  });

  function handleNodeClick(_: React.MouseEvent, node: { id: string }) {
    const next = node.id === selectedId ? null : node.id;
    setSelectedId(next);
    if (next) onNodeClick?.(next);
  }

  // Derive announcement text for the selected node
  const selectedLabel = selectedId
    ? (rawNodes.find((n) => n.id === selectedId)?.data?.label as string | undefined) ?? selectedId
    : "";

  return (
    <div className="h-full w-full" role="application" aria-label="Grafo de conocimiento">
      {/* Visually-hidden live region for screen readers */}
      <span
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {selectedLabel ? `Nodo seleccionado: ${selectedLabel}` : ""}
      </span>
      <ReactFlow nodes={nodes} edges={edges} fitView onNodeClick={handleNodeClick}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
