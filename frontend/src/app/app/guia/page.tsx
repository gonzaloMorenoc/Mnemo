"use client";

import { useLayoutEffect, useState } from "react";

import { CHAPTERS, CHAPTER_SLUGS } from "@/content/guia";
import { GuiaContent } from "@/components/guia/GuiaContent";
import { GuiaSidebar } from "@/components/guia/GuiaSidebar";

const CHAPTER_INDEX = new Set(CHAPTER_SLUGS);

export default function GuiaPage() {
  // Deep-link a un capítulo (?c=slug). useLayoutEffect corre antes del pintado →
  // sin flash del capítulo por defecto. (window.location, no useSearchParams, para
  // no forzar Suspense — mismo patrón que knowledge/page.tsx.)
  const [slug, setSlug] = useState(CHAPTERS[0].slug);
  useLayoutEffect(() => {
    const c = new URLSearchParams(window.location.search).get("c");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (c && CHAPTER_INDEX.has(c)) setSlug(c);
  }, []);

  const active = CHAPTERS.find((c) => c.slug === slug) ?? CHAPTERS[0];
  const chapterLinks = CHAPTERS.map((c) => ({ slug: c.slug, title: c.title }));

  return (
    <div className="space-y-6">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">
        Guía · Cómo funciona Mnemo
      </p>
      <div className="grid gap-8 md:grid-cols-[220px_1fr]">
        <aside className="md:sticky md:top-6 md:self-start">
          <GuiaSidebar chapters={chapterLinks} activeSlug={active.slug} />
        </aside>
        <GuiaContent chapter={active} />
      </div>
    </div>
  );
}
