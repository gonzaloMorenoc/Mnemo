// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GLOSSARY } from "@/lib/glossary";
import { Tooltip, TooltipContent, TooltipTrigger } from "../tooltip";
import { InfoTooltip } from "../InfoTooltip";

/** Renders the primitives directly with the tooltip forced open (avoids hover/timer). */
function InfoTooltipOpen({ term, content, label }: { term?: string; content?: string; label?: string }) {
  const text = content ?? (term ? GLOSSARY[term] : "") ?? "";
  return (
    <Tooltip open>
      <TooltipTrigger asChild>
        <button type="button" aria-label={label ?? `Qué es: ${term ?? "ayuda"}`}>?</button>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  );
}

describe("InfoTooltip", () => {
  it("renders a button with default aria-label when no term or label given", () => {
    render(<InfoTooltip content="Texto de ayuda" />);
    const btn = screen.getByRole("button");
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute("aria-label", "Qué es: ayuda");
  });

  it("renders aria-label derived from term", () => {
    render(<InfoTooltip term="foso" />);
    const btn = screen.getByRole("button", { name: /Qué es: foso/i });
    expect(btn).toBeInTheDocument();
  });

  it("uses explicit label prop over the default", () => {
    render(<InfoTooltip term="triaje" label="Más sobre triaje" />);
    const btn = screen.getByRole("button", { name: "Más sobre triaje" });
    expect(btn).toBeInTheDocument();
  });

  it("exposes the glossary text for the given term (forced open)", () => {
    render(<InfoTooltipOpen term="foso" />);
    // Radix renders the text twice (visible content + hidden aria span);
    // query by role="tooltip" to get the aria span, or use getAllByText
    const matches = screen.getAllByText(
      "El foso: tus correcciones acumuladas que calibran el motor de triaje.",
    );
    expect(matches.length).toBeGreaterThan(0);
  });

  it("uses explicit content prop over glossary lookup (forced open)", () => {
    render(<InfoTooltipOpen term="foso" content="Override text" />);
    const matches = screen.getAllByText("Override text");
    expect(matches.length).toBeGreaterThan(0);
  });
});
