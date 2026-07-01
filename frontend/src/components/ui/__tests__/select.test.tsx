// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../select";

// Radix UI uses pointer/scroll APIs not available in jsdom
beforeEach(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => undefined;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => undefined;
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
});

afterEach(() => {
  cleanup();
});

function TestSelect({ onValueChange }: { onValueChange: (v: string) => void }) {
  return (
    <Select onValueChange={onValueChange}>
      <SelectTrigger aria-label="Choose option">
        <SelectValue placeholder="Elige..." />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="alpha">Alpha</SelectItem>
        <SelectItem value="beta">Beta</SelectItem>
      </SelectContent>
    </Select>
  );
}

describe("Select", () => {
  it("calls onValueChange with the selected value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    const { container } = render(<TestSelect onValueChange={onChange} />);

    // Open the select — use container to scope the click to this instance
    await user.click(within(container).getByRole("combobox", { name: "Choose option" }));

    // Wait for options to appear and pick the first option
    const alpha = await screen.findByRole("option", { name: "Alpha" });
    await user.click(alpha);

    expect(onChange).toHaveBeenCalledWith("alpha");
  });

  it("calls onValueChange with the second option value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    const { container } = render(<TestSelect onValueChange={onChange} />);

    await user.click(within(container).getByRole("combobox", { name: "Choose option" }));

    const beta = await screen.findByRole("option", { name: "Beta" });
    await user.click(beta);

    expect(onChange).toHaveBeenCalledWith("beta");
  });
});
