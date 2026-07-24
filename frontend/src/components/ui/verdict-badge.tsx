import { Badge } from "@/components/ui/badge";

/**
 * Paleta semántica de veredictos: el color ES información en QA.
 * apto=verde · apto-con-reservas=ámbar · no-apto=rojo · sin_confirmar/sin acta=neutro.
 */
const VERDICT_STYLE: Record<string, string> = {
  apto: "border-emerald-200 bg-emerald-100 text-emerald-800",
  "apto-con-reservas": "border-amber-200 bg-amber-100 text-amber-800",
  "no-apto": "border-red-200 bg-red-100 text-red-800",
  sin_confirmar: "border-slate-200 bg-slate-100 text-slate-700",
};

const VERDICT_LABEL: Record<string, string> = {
  apto: "Apto",
  "apto-con-reservas": "Apto con reservas",
  "no-apto": "No apto",
  sin_confirmar: "Sin confirmar",
};

export function VerdictBadge({ verdict }: { verdict?: string | null }) {
  if (!verdict) {
    return <Badge className="border-zinc-200 bg-zinc-50 text-zinc-500">Sin veredicto aún</Badge>;
  }
  return (
    <Badge className={VERDICT_STYLE[verdict] ?? ""}>
      {VERDICT_LABEL[verdict] ?? verdict}
    </Badge>
  );
}
