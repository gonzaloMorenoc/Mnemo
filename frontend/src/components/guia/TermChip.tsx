import { GLOSSARY } from "@/lib/glossary";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

/**
 * Nombres propios de términos cuyo slug quedaría crudo con solo cambiar "_"→espacio
 * (acento o gramática). En minúscula para que encajen tanto inline como de título;
 * el `GLOSSARY` sigue siendo la única fuente de las *definiciones*, esto solo nombra.
 */
const TERM_LABELS: Record<string, string> = {
  calibracion: "calibración",
  self_heal: "autoreparación",
  acciones_nivel2: "acciones de Nivel 2",
  precision_motor: "precisión del motor",
  familia_defectos: "familia de defectos",
  tipo_conocimiento: "tipo de conocimiento",
};

/** Slug del glosario → texto legible ("risk_score" → "risk score"). */
export function prettyTerm(term: string): string {
  return TERM_LABELS[term] ?? term.replace(/_/g, " ");
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
