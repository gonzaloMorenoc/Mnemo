import { describe, expect, it } from "vitest";

import type { Graph } from "@/lib/api/types";
import { toFlow } from "./graph-layout";

const EMPTY_GRAPH: Graph = { nodes: [], edges: [] };

const GRAPH: Graph = {
  nodes: [
    { id: "n1", type: "knowledge", label: "Auth flows", kind: "lesson" },
    { id: "n2", type: "defect", label: "Flaky login", kind: "bug" },
    { id: "n3", type: "domain", label: "Payments", count: 3 },
  ],
  edges: [
    { source: "n1", target: "n2", relation: "documenta" },
    { source: "n2", target: "n3", relation: "pertenece" },
  ],
};

describe("toFlow — node mapping", () => {
  it("returns the same number of nodes as the graph", () => {
    const { nodes } = toFlow(GRAPH);
    expect(nodes).toHaveLength(3);
  });

  it("preserves node ids", () => {
    const { nodes } = toFlow(GRAPH);
    expect(nodes.map((n) => n.id)).toEqual(["n1", "n2", "n3"]);
  });

  it("sets data.label from graph node label", () => {
    const { nodes } = toFlow(GRAPH);
    expect(nodes[0].data.label).toBe("Auth flows");
    expect(nodes[1].data.label).toBe("Flaky login");
    expect(nodes[2].data.label).toBe("Payments");
  });

  it("assigns className 'node-knowledge' for type=knowledge", () => {
    const { nodes } = toFlow(GRAPH);
    expect(nodes[0].className).toContain("node-knowledge");
  });

  it("assigns className 'node-defect' for type=defect", () => {
    const { nodes } = toFlow(GRAPH);
    expect(nodes[1].className).toContain("node-defect");
  });

  it("assigns className 'node-domain' for type=domain", () => {
    const { nodes } = toFlow(GRAPH);
    expect(nodes[2].className).toContain("node-domain");
  });

  it("gives each node a position with numeric x and y", () => {
    const { nodes } = toFlow(GRAPH);
    for (const node of nodes) {
      expect(typeof node.position.x).toBe("number");
      expect(typeof node.position.y).toBe("number");
    }
  });

  it("positions are deterministic (same graph → same positions)", () => {
    const first = toFlow(GRAPH).nodes;
    const second = toFlow(GRAPH).nodes;
    for (let i = 0; i < first.length; i++) {
      expect(first[i].position).toEqual(second[i].position);
    }
  });

  it("different nodes get different positions", () => {
    const { nodes } = toFlow(GRAPH);
    const positions = nodes.map((n) => `${n.position.x},${n.position.y}`);
    const unique = new Set(positions);
    expect(unique.size).toBe(nodes.length);
  });
});

describe("toFlow — edge mapping", () => {
  it("returns the same number of edges as the graph", () => {
    const { edges } = toFlow(GRAPH);
    expect(edges).toHaveLength(2);
  });

  it("preserves source and target", () => {
    const { edges } = toFlow(GRAPH);
    expect(edges[0].source).toBe("n1");
    expect(edges[0].target).toBe("n2");
    expect(edges[1].source).toBe("n2");
    expect(edges[1].target).toBe("n3");
  });

  it("sets edge label from relation field", () => {
    const { edges } = toFlow(GRAPH);
    expect(edges[0].label).toBe("documenta");
    expect(edges[1].label).toBe("pertenece");
  });

  it("each edge has a unique id", () => {
    const { edges } = toFlow(GRAPH);
    const ids = edges.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("toFlow — empty graph", () => {
  it("returns empty nodes and edges for an empty graph", () => {
    const { nodes, edges } = toFlow(EMPTY_GRAPH);
    expect(nodes).toHaveLength(0);
    expect(edges).toHaveLength(0);
  });
});
