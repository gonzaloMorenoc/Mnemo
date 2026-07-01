// @vitest-environment jsdom
/**
 * Smoke tests for KnowledgeGraphView.
 *
 * react-flow internally uses ResizeObserver and DOMMatrix, which are not
 * available in jsdom. We shim them here so the component can at least mount
 * without crashing.  Deep interaction tests (fit-view, zoom, pan) require a
 * real browser — those live in E2E tests instead.
 *
 * The CSS import (`@xyflow/react/dist/style.css`) is mocked so vitest/jsdom
 * doesn't trip over raw stylesheet files.
 */

// Mock CSS import before any component code runs
vi.mock("@xyflow/react/dist/style.css", () => ({}));

import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { Graph } from "@/lib/api/types";
import { KnowledgeGraphView } from "./knowledge-graph-view";

// ─── jsdom shims required by react-flow ─────────────────────────────────────

beforeAll(() => {
  // ResizeObserver shim
  if (typeof globalThis.ResizeObserver === "undefined") {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }

  // DOMMatrix shim (used internally by @xyflow/system for transforms)
  if (typeof globalThis.DOMMatrix === "undefined") {
    globalThis.DOMMatrix = class {
      a = 1;
      b = 0;
      c = 0;
      d = 1;
      e = 0;
      f = 0;
      constructor() {}
      inverse() {
        return this;
      }
      multiply() {
        return this;
      }
      scale() {
        return this;
      }
      translate() {
        return this;
      }
    } as unknown as typeof DOMMatrix;
  }

  // SVGSVGElement.createSVGMatrix shim
  if (typeof SVGSVGElement !== "undefined" && !SVGSVGElement.prototype.createSVGMatrix) {
    SVGSVGElement.prototype.createSVGMatrix = function () {
      return {
        a: 1,
        b: 0,
        c: 0,
        d: 1,
        e: 0,
        f: 0,
        multiply: () => this,
        translate: () => this,
        scale: () => this,
        inverse: () => this,
      } as unknown as SVGMatrix;
    };
  }
});

// ─── fixtures ────────────────────────────────────────────────────────────────

const GRAPH: Graph = {
  nodes: [
    { id: "n1", type: "knowledge", label: "Auth flows", kind: "lesson" },
    { id: "n2", type: "defect", label: "Flaky login" },
    { id: "n3", type: "domain", label: "Payments", count: 3 },
  ],
  edges: [
    { source: "n1", target: "n2", relation: "documenta" },
    { source: "n2", target: "n3", relation: "pertenece" },
  ],
};

const EMPTY_GRAPH: Graph = { nodes: [], edges: [] };

// ─── tests ───────────────────────────────────────────────────────────────────

describe("KnowledgeGraphView", () => {
  it("renders without crashing for a non-empty graph", () => {
    render(<KnowledgeGraphView graph={GRAPH} />);
    // react-flow renders the wrapper div; it doesn't need any assertion beyond
    // "no throw", but we also check the container exists.
    expect(document.querySelector(".react-flow")).not.toBeNull();
  });

  it("shows 'sin datos' message for an empty graph", () => {
    render(<KnowledgeGraphView graph={EMPTY_GRAPH} />);
    expect(screen.getByText(/sin datos/i)).toBeInTheDocument();
  });

  it("calls onNodeClick when provided (smoke: not crashing on undefined)", () => {
    const onNodeClick = vi.fn();
    // Just assert it renders without error even when onNodeClick is provided
    render(<KnowledgeGraphView graph={GRAPH} onNodeClick={onNodeClick} />);
    expect(document.querySelector(".react-flow")).not.toBeNull();
  });

  it("el contenedor del grafo tiene aria-label='Grafo de conocimiento'", () => {
    render(<KnowledgeGraphView graph={GRAPH} />);
    const container = document.querySelector('[aria-label="Grafo de conocimiento"]');
    expect(container).not.toBeNull();
  });

  it("existe una región aria-live='polite' para anuncios de nodo seleccionado", () => {
    render(<KnowledgeGraphView graph={GRAPH} />);
    const liveRegion = document.querySelector('[aria-live="polite"]');
    expect(liveRegion).not.toBeNull();
  });
});
