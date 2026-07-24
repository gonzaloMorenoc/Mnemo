import { GLOSSARY } from "@/lib/glossary";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

/** Slug del glosario → texto legible ("risk_score" → "risk score"). */
export function prettyTerm(term: string): string {
  return term.replace(/_/g, " ");
}

/**
 * Renderiza un término del GLOSSARY inline: el texto + un InfoTooltip con su
 * definición. Si el término no está en el glosario, muestra solo el texto.
 */
export function TermChip({ term }: { term: string }) {
  const label = prettyTerm(term);
  if (!GLOSSARY[term]) return <span>{label}</span>;
  return (
    <span className="inline-flex items-center gap-0.5 font-medium text-zinc-700">
      {label}
      <InfoTooltip term={term} />
    </span>
  );
}
