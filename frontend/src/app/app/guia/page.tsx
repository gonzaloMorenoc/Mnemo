"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { CHAPTERS, CHAPTER_SLUGS } from "@/content/guia";
import { GuiaContent } from "@/components/guia/GuiaContent";
import { GuiaSidebar } from "@/components/guia/GuiaSidebar";

const CHAPTER_INDEX = new Set(CHAPTER_SLUGS);

function GuiaView() {
  // El capítulo activo se DERIVA de ?c= (reactivo): al pulsar un capítulo, la
  // navegación suave cambia la query y useSearchParams re-renderiza sin remontar
  // — por eso no hace falta refrescar. Slug ausente/desconocido → primer capítulo.
  const params = useSearchParams();
  const c = params.get("c");
  const slug = c && CHAPTER_INDEX.has(c) ? c : CHAPTERS[0].slug;
  const active = CHAPTERS.find((x) => x.slug === slug) ?? CHAPTERS[0];
  const chapterLinks = CHAPTERS.map((x) => ({ slug: x.slug, title: x.title }));

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

export default function GuiaPage() {
  // useSearchParams exige un límite de Suspense en el App Router.
  return (
    <Suspense fallback={null}>
      <GuiaView />
    </Suspense>
  );
}
