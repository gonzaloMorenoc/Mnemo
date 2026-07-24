// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

import { LatestReleaseHero } from "@/components/dashboard/LatestReleaseHero";
import type { RunListItem, ExecutionManifest } from "@/lib/api/types";

afterEach(cleanup);

const RUN: RunListItem = {
  id: "r1", project: "checkout-suite", source: "junit", commit_sha: "a1b2c3d4e5",
  created_at: "2026-07-22T10:00:00+00:00", verdict: "apto", risk_score: 42, failures: 5,
};
const MANIFEST: ExecutionManifest = {
  total: 128, passed: 120, failed: 5, skipped: 3, complete: true, source_format: "junit", artifact_sha256: "x",
};

describe("LatestReleaseHero", () => {
  it("certified=true + manifest: veredicto, chip 'acta firmada', manifiesto y medidor de riesgo", () => {
    render(<LatestReleaseHero run={RUN} manifest={MANIFEST} certified={true} />);
    expect(screen.getByText("Apto")).toBeInTheDocument();
    expect(screen.getByText(/acta firmada/i)).toBeInTheDocument();
    expect(screen.getByText(/128 tests · 120 ✓ · 5 ✗/)).toBeInTheDocument();
    expect(screen.getByText("42/100")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver run/i })).toHaveAttribute("href", "/app/autopilot");
  });

  it("certified=true + manifest=null (acta v2 sin manifiesto): el chip SIGUE mostrándose y se ven los fallos", () => {
    render(<LatestReleaseHero run={RUN} manifest={null} certified={true} />);
    expect(screen.getByText(/acta firmada/i)).toBeInTheDocument();
    expect(screen.getByText(/5 fallos/)).toBeInTheDocument();
  });

  it("certified=false + manifest=null: no hay acta → muestra '{failures} fallos' y NO el chip", () => {
    render(<LatestReleaseHero run={RUN} manifest={null} certified={false} />);
    expect(screen.getByText(/5 fallos/)).toBeInTheDocument();
    expect(screen.queryByText(/acta firmada/i)).toBeNull();
  });

  it("verdict sin_confirmar: el riesgo es '—', no un número", () => {
    render(<LatestReleaseHero run={{ ...RUN, verdict: "sin_confirmar" }} manifest={null} certified={false} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("42/100")).toBeNull();
  });
});
