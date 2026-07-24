import Link from "next/link";

import { TermChip } from "@/components/guia/TermChip";

// Un solo escaneo. Orden de alternativas: negrita, código, [[termino]], enlace.
// [[termino]] va ANTES que el enlace para que "[[x]]" no lo capture el patrón de enlace.
// Los enlaces solo se aceptan internos (empiezan por "/").
const TOKEN =
  /\*\*(.+?)\*\*|`([^`]+?)`|\[\[([^\]]+?)\]\]|\[([^\]]+?)\]\((\/[^)]+?)\)/g;

/**
 * Parser inline deliberadamente tonto: cuatro tokens NO anidados. El texto plano
 * se emite como nodos de texto de React (auto-escapados: "<" nunca es HTML).
 */
export function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(TOKEN)) {
    const start = m.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    const [, bold, code, term, linkText, linkHref] = m;
    if (bold !== undefined) {
      nodes.push(<strong key={key++}>{bold}</strong>);
    } else if (code !== undefined) {
      nodes.push(
        <code key={key++} className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-[0.85em]">
          {code}
        </code>,
      );
    } else if (term !== undefined) {
      nodes.push(<TermChip key={key++} term={term} />);
    } else if (linkText !== undefined && linkHref !== undefined) {
      nodes.push(
        <Link key={key++} href={linkHref} className="font-medium text-primary underline underline-offset-2">
          {linkText}
        </Link>,
      );
    }
    last = start + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
