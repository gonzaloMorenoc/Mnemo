/**
 * Banda de riesgo del índice de continuidad: lo que el número significa para
 * quien decide una rotación. Los textos dicen lo que el índice mide —cuánto del
 * proyecto está documentado en Mnemo—, nunca un porcentaje de «lo que se sabe».
 */
export type BandKey = "alto" | "medio" | "cubierto" | "sin-datos";

export interface Band {
  key: BandKey;
  label: string;
  headline: string;
  /** Clases de Tailwind: texto del número, relleno de la barra y chip. */
  text: string;
  bar: string;
  chip: string;
}

const BANDS: Record<BandKey, Omit<Band, "key">> = {
  alto: {
    label: "Riesgo alto",
    headline: "Si rota quien lleva este proyecto, se iría conocimiento que aquí no consta.",
    text: "text-red-700",
    bar: "bg-red-500",
    chip: "border-red-200 bg-red-50 text-red-700",
  },
  medio: {
    label: "Riesgo medio",
    headline: "Hay huecos que se irían con la persona: complétalos antes del traspaso.",
    text: "text-amber-700",
    bar: "bg-amber-500",
    chip: "border-amber-200 bg-amber-50 text-amber-800",
  },
  cubierto: {
    label: "Cubierto",
    headline: "Quien llegue encontrará el proyecto documentado en Mnemo.",
    text: "text-emerald-700",
    bar: "bg-emerald-500",
    chip: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  "sin-datos": {
    label: "Sin datos",
    headline: "Aún no hay datos suficientes para medir este proyecto.",
    text: "text-zinc-500",
    bar: "bg-zinc-300",
    chip: "border-zinc-200 bg-zinc-50 text-zinc-600",
  },
};

export function continuityBand(score: number | null): Band {
  const key: BandKey =
    score === null ? "sin-datos" : score < 50 ? "alto" : score < 80 ? "medio" : "cubierto";
  return { key, ...BANDS[key] };
}

export function deltaDesdeActa(actual: number | null, ultimaActa: number | null): string | null {
  if (actual === null || ultimaActa === null) return null;
  const d = actual - ultimaActa;
  if (d === 0) return "igual que en la última acta";
  return `${d > 0 ? "+" : "−"}${Math.abs(d)} desde la última acta`;
}
