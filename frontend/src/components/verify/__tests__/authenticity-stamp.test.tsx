// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuthenticityStamp } from "@/components/verify/AuthenticityStamp";

const BASE = {
  schema: "mnemo.cert.v3",
  verdict: "no-apto",
  risk_score: 72,
  identity: { project: "checkout-suite", commit_sha: "a1b2c3d4e5f6a7b8",
              run_id: "r1", created_at: "2026-07-24T10:00:00Z", key_id: "946152583e361f1e" },
  execution_manifest: { total: 128, passed: 120, failed: 5, skipped: 3, flaky: 0 },
};

// Mismos campos que BASE pero SIN `execution_manifest` (acta v2): se define como
// literal aparte -en vez de desestructurar BASE para omitir la clave- porque esa
// desestructuración deja una variable sin usar que el lint rechaza.
const BASE_SIN_MANIFIESTO = {
  schema: "mnemo.cert.v2",
  verdict: "no-apto",
  risk_score: 72,
  identity: { project: "checkout-suite", commit_sha: "a1b2c3d4e5f6a7b8",
              run_id: "r1", created_at: "2026-07-24T10:00:00Z", key_id: "946152583e361f1e" },
};

afterEach(cleanup);

describe("AuthenticityStamp", () => {
  it("separa autenticidad de veredicto: un acta auténtica puede ser NO APTO", () => {
    render(<AuthenticityStamp canonical={BASE} />);
    expect(screen.getByText(/acta auténtica/i)).toBeInTheDocument();
    expect(screen.getByText("No apto")).toBeInTheDocument();
    expect(screen.getByText(/72\/100/)).toBeInTheDocument();
  });

  it("acta v2 sin manifiesto: no rompe ni deja hueco", () => {
    render(<AuthenticityStamp canonical={BASE_SIN_MANIFIESTO} />);
    expect(screen.getByText(/acta auténtica/i)).toBeInTheDocument();
    expect(screen.queryByText(/tests ·/)).toBeNull();
  });

  it("key_id vacío: omite la línea de clave y no pinta 'undefined'", () => {
    render(<AuthenticityStamp canonical={{ ...BASE, identity: { ...BASE.identity, key_id: "" } }} />);
    expect(screen.queryByText(/clave/i)).toBeNull();
    expect(screen.queryByText(/undefined/i)).toBeNull();
  });

  it("sin_confirmar: el riesgo es una raya, no un 0", () => {
    render(<AuthenticityStamp canonical={{ ...BASE, verdict: "sin_confirmar", risk_score: 0 }} />);
    expect(screen.getByText("Sin confirmar")).toBeInTheDocument();
    expect(screen.queryByText(/0\/100/)).toBeNull();
  });
});
