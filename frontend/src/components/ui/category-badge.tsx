import { Badge } from "@/components/ui/badge";

/**
 * Paleta semántica de categorías de triaje (el color ES información):
 * real=rojo · flaky=ámbar · mantenimiento=azul · infra=violeta · sin etiquetar=neutro.
 */
export const CATEGORY_STYLE: Record<string, string> = {
  real: "border-red-200 bg-red-100 text-red-800",
  flaky: "border-amber-200 bg-amber-100 text-amber-800",
  maintenance: "border-blue-200 bg-blue-100 text-blue-800",
  infra: "border-violet-200 bg-violet-100 text-violet-800",
  unknown: "border-zinc-200 bg-zinc-50 text-zinc-500",
};

export const CATEGORY_LABEL: Record<string, string> = {
  real: "Fallo real",
  flaky: "Flaky",
  maintenance: "Mantenimiento",
  infra: "Infraestructura",
  unknown: "Sin etiquetar",
};

export function CategoryBadge({ category, count }: { category: string; count?: number }) {
  return (
    <Badge className={CATEGORY_STYLE[category] ?? ""}>
      {CATEGORY_LABEL[category] ?? category}
      {count !== undefined ? `: ${count}` : ""}
    </Badge>
  );
}
