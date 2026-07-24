import { cn } from "@/lib/utils";

function riskColor(score: number): string {
  if (score <= 33) return "bg-emerald-500";
  if (score <= 66) return "bg-amber-500";
  return "bg-red-500";
}

/** Medidor de riesgo 0..100 (verde→rojo). "—" si score es null (sin_confirmar / sin dato). */
export function RiskMeter({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <span aria-label="Riesgo: no aplica" className="text-zinc-400">
        —
      </span>
    );
  }
  const pct = Math.max(0, Math.min(100, score));
  return (
    <span role="img" aria-label={`Riesgo: ${pct} de 100`} className="flex items-center gap-2">
      <span className="h-2 w-24 rounded-full bg-zinc-100">
        <span className={cn("block h-2 rounded-full", riskColor(pct))} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-sm font-medium tabular-nums text-zinc-900">{pct}/100</span>
    </span>
  );
}
