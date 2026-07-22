import type { Edge, Node } from "@xyflow/react";
import type React from "react";

import type { Graph, GraphEdge, GraphNode } from "@/lib/api/types";

// ─── layout constants ────────────────────────────────────────────────────────
const MIN_RADIUS = 220; // px — radio mínimo del layout circular
const NODE_ARC = 200;   // px de circunferencia por nodo (ancho típico + hueco)
const CENTER_X = 300;
const CENTER_Y = 300;

// ─── color class by node type ────────────────────────────────────────────────
const NODE_CLASS: Record<GraphNode["type"], string> = {
  knowledge: "node-knowledge",
  defect: "node-defect",
  domain: "node-domain",
};

// Estilos inline por tipo: el CSS de globals apuntaba a un DOM de react-flow
// antiguo y los nodos salían monocromos. Inline garantiza el color semántico.
const NODE_STYLE: Record<GraphNode["type"], React.CSSProperties> = {
  knowledge: { background: "#dbeafe", border: "1px solid #93c5fd", color: "#1e40af" },
  defect: { background: "#fee2e2", border: "1px solid #fca5a5", color: "#991b1b" },
  domain: { background: "#f4f4f5", border: "1px solid #a1a1aa", color: "#3f3f46" },
};

// ─── pure mapping helpers ────────────────────────────────────────────────────

function mapNode(node: GraphNode, index: number, total: number): Node {
  const angle = total > 1 ? (2 * Math.PI * index) / total : 0;
  // El radio crece con el nº de nodos: con radio fijo, a partir de ~10 nodos
  // las cajas se solapaban hasta ser ilegibles.
  const radius = Math.max(MIN_RADIUS, Math.round((total * NODE_ARC) / (2 * Math.PI)));
  const position =
    total === 1
      ? { x: CENTER_X, y: CENTER_Y }
      : {
          x: Math.round(CENTER_X + radius * Math.cos(angle)),
          y: Math.round(CENTER_Y + radius * Math.sin(angle)),
        };

  return {
    id: node.id,
    type: "default",
    position,
    data: { label: node.label },
    className: NODE_CLASS[node.type],
    style: NODE_STYLE[node.type],
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
