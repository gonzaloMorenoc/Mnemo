// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

import { GuiaSidebar } from "@/components/guia/GuiaSidebar";

afterEach(cleanup);

const CHS = [
  { slug: "uno", title: "Capítulo uno" },
  { slug: "dos", title: "Capítulo dos" },
];

describe("GuiaSidebar", () => {
  it("lista un enlace por capítulo, apuntando a ?c=<slug>", () => {
    render(<GuiaSidebar chapters={CHS} activeSlug="uno" />);
    expect(screen.getByRole("link", { name: "Capítulo uno" })).toHaveAttribute("href", "/app/guia?c=uno");
    expect(screen.getByRole("link", { name: "Capítulo dos" })).toHaveAttribute("href", "/app/guia?c=dos");
  });

  it("marca el capítulo activo con aria-current", () => {
    render(<GuiaSidebar chapters={CHS} activeSlug="dos" />);
    expect(screen.getByRole("link", { name: "Capítulo dos" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Capítulo uno" })).not.toHaveAttribute("aria-current");
  });
});
