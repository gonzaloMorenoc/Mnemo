import { GLOSSARY } from "@/lib/glossary";
import { renderInline } from "@/components/guia/renderInline";
import { prettyTerm } from "@/components/guia/TermChip";
import type { Block, Chapter, Section } from "@/content/guia/types";

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "p":
      return <p className="leading-relaxed text-zinc-700">{renderInline(block.text)}</p>;
    case "steps":
      return (
        <ol className="list-decimal space-y-1.5 pl-5 text-zinc-700">
          {block.items.map((it, i) => (
            <li key={i}>{renderInline(it)}</li>
          ))}
        </ol>
      );
    case "list":
      return (
        <ul className="list-disc space-y-1.5 pl-5 text-zinc-700">
          {block.items.map((it, i) => (
            <li key={i}>{renderInline(it)}</li>
          ))}
        </ul>
      );
    case "note":
      return (
        <div
          className={
            block.tone === "warn"
              ? "rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
              : "rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900"
          }
        >
          {renderInline(block.text)}
        </div>
      );
    case "term":
      return (
        <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
          <dt className="font-medium text-zinc-900">{prettyTerm(block.term)}</dt>
          <dd className="mt-0.5 text-sm text-zinc-600">{GLOSSARY[block.term] ?? ""}</dd>
        </div>
      );
  }
}

function SectionView({ section }: { section: Section }) {
  return (
    <section className="space-y-3">
      {section.heading && (
        <h2 className="text-lg font-semibold tracking-tight text-zinc-900">{section.heading}</h2>
      )}
      {section.blocks.map((block, i) => (
        <BlockView key={i} block={block} />
      ))}
    </section>
  );
}

export function GuiaContent({ chapter }: { chapter: Chapter }) {
  return (
    <article className="max-w-2xl space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{chapter.title}</h1>
        <p className="text-sm text-zinc-500">{chapter.summary}</p>
      </header>
      {chapter.sections.map((section, i) => (
        <SectionView key={i} section={section} />
      ))}
    </article>
  );
}
