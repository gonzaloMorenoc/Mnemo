import { describe, expect, it } from "vitest";

import { CHAPTERS } from "@/content/guia";
import { NAV_ITEMS } from "@/components/layout/nav";

const NAV_HREFS = new Set(NAV_ITEMS.map((i) => i.href));
const LINK = /\[[^\]]+\]\((\/[^)]+)\)/g;

/** Extrae todos los destinos de enlace [texto](/ruta) del texto de un capítulo. */
function linksIn(text: string): string[] {
  return [...text.matchAll(LINK)].map((m) => m[1].split("?")[0]); // sin query
}

function chapterTexts(): string[] {
  const out: string[] = [];
  for (const c of CHAPTERS) {
    for (const s of c.sections) {
      for (const b of s.blocks) {
        if (b.kind === "p" || b.kind === "note") out.push(b.text);
        if (b.kind === "steps" || b.kind === "list") out.push(...b.items);
      }
    }
  }
  return out;
}

describe("Guía — integridad de enlaces internos", () => {
  it("todo enlace interno de un capítulo apunta a una ruta real del nav", () => {
    const bad: string[] = [];
    for (const text of chapterTexts()) {
      for (const href of linksIn(text)) {
        if (!NAV_HREFS.has(href)) bad.push(href);
      }
    }
    expect(bad).toEqual([]);
  });

  it("ningún [[termino]] queda dentro de **negrita** (el parser no anida)", () => {
    const BOLD = /\*\*(.+?)\*\*/g;
    const bad: string[] = [];
    for (const text of chapterTexts()) {
      for (const m of text.matchAll(BOLD)) {
        if (m[1].includes("[[")) bad.push(m[0]);
      }
    }
    expect(bad).toEqual([]);
  });

  it("hay 7 capítulos con los slugs esperados en orden", () => {
    expect(CHAPTERS.map((c) => c.slug)).toEqual([
      "que-es-mnemo",
      "primeros-pasos",
      "analizar-un-run",
      "el-acta-firmada",
      "la-memoria-de-qa",
      "familias-y-calibracion",
      "preguntas-frecuentes",
    ]);
  });
});
