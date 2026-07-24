import { describe, expect, it } from "vitest";

import { CHAPTERS, CHAPTER_SLUGS } from "@/content/guia";

describe("registro de capítulos de la Guía", () => {
  it("expone al menos un capítulo", () => {
    expect(CHAPTERS.length).toBeGreaterThan(0);
  });

  it("todos los capítulos tienen slug, título y resumen no vacíos", () => {
    for (const c of CHAPTERS) {
      expect(c.slug).toBeTruthy();
      expect(c.title).toBeTruthy();
      expect(c.summary).toBeTruthy();
      expect(Array.isArray(c.sections)).toBe(true);
    }
  });

  it("los slugs son únicos y CHAPTER_SLUGS los refleja en orden", () => {
    const slugs = CHAPTERS.map((c) => c.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    expect(CHAPTER_SLUGS).toEqual(slugs);
  });
});
