import { cn } from "@/lib/utils";

const W = 120;
const H = 32;
const P = 2;

/** Polyline de una serie numérica (valores ya cronológicos, sin nulos). null si <2. */
export function Sparkline({ values, ariaLabel, className }: { values: number[]; ariaLabel: string; className?: string }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = P + (i * (W - 2 * P)) / (values.length - 1);
      const y = H - P - ((v - min) / span) * (H - 2 * P);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg role="img" aria-label={ariaLabel} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={cn("h-8 w-full text-primary", className)}>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
