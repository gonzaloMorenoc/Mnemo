import Link from "next/link";

import { cn } from "@/lib/utils";

export function GuiaSidebar({
  chapters,
  activeSlug,
}: {
  chapters: { slug: string; title: string }[];
  activeSlug: string;
}) {
  return (
    <nav aria-label="Capítulos de la Guía" className="space-y-1">
      {chapters.map((c) => {
        const active = c.slug === activeSlug;
        return (
          <Link
            key={c.slug}
            href={`/app/guia?c=${c.slug}`}
            aria-current={active ? "page" : undefined}
            className={cn(
              "block rounded-lg px-3 py-2 text-sm transition",
              active
                ? "bg-primary text-white"
                : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900",
            )}
          >
            {c.title}
          </Link>
        );
      })}
    </nav>
  );
}
