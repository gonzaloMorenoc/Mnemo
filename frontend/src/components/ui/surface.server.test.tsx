// @vitest-environment node
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Surface } from "./surface";

describe("Surface", () => {
  it("renders title and description", () => {
    const html = renderToStaticMarkup(
      <Surface title="Analyze" description="Paste logs" />,
    );

    expect(html).toContain("Analyze");
    expect(html).toContain("Paste logs");
  });
});
