import type { Edge, Node } from "@xyflow/react";

import type { Graph, GraphEdge, GraphNode } from "@/lib/api/types";

// ─── layout constants ────────────────────────────────────────────────────────
const RADIUS = 220; // px — circle radius for circular layout
const CENTER_X = 300;
const CENTER_Y = 300;

// ─── color class by node type ────────────────────────────────────────────────
const NODE_CLASS: Record<GraphNode["type"], string> = {
  knowledge: "node-knowledge",
  defect: "node-defect",
  domain: "node-domain",
};

// ─── pure mapping helpers ────────────────────────────────────────────────────

function mapNode(node: GraphNode, index: number, total: number): Node {
  const angle = total > 1 ? (2 * Math.PI * index) / total : 0;
  const position =
    total === 1
      ? { x: CENTER_X, y: CENTER_Y }
      : {
          x: Math.round(CENTER_X + RADIUS * Math.cos(angle)),
          y: Math.round(CENTER_Y + RADIUS * Math.sin(angle)),
        };

  return {
    id: node.id,
    type: "default",
    position,
    data: { label: node.label },
    className: NODE_CLASS[node.type],
  };
}

function mapEdge(edge: GraphEdge, index: number): Edge {
  return {
    id: `e-${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.relation,
  };
}

// ─── public API ──────────────────────────────────────────────────────────────

/**
 * Pure, deterministic mapping from a domain Graph to react-flow nodes + edges.
 * No randomness; positions are calculated from index in a circular layout.
 */
export function toFlow(graph: Graph): { nodes: Node[]; edges: Edge[] } {
  const total = graph.nodes.length;
  return {
    nodes: graph.nodes.map((n, i) => mapNode(n, i, total)),
    edges: graph.edges.map((e, i) => mapEdge(e, i)),
  };
}
