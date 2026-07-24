import { cn } from "@/lib/utils";

const VERDICT_META: { key: string; label: string; bar: string }[] = [
  { key: "apto", label: "Apto", bar: "bg-emerald-500" },
  { key: "apto-con-reservas", label: "Con reservas", bar: "bg-amber-500" },
  { key: "no-apto", label: "No apto", bar: "bg-red-500" },
  { key: "sin_confirmar", label: "Sin confirmar", bar: "bg-slate-400" },
];

/** Barras horizontales por veredicto presente, con el color semántico de verdict-badge. */
export function VerdictBar({ counts }: { counts: Record<string, number> }) {
  const rows = VERDICT_META.map((v) => ({ ...v, n: counts[v.key] ?? 0 })).filter((v) => v.n > 0);
  const total = rows.reduce((s, r) => s + r.n, 0);
  if (total === 0) return <p className="text-sm text-zinc-500">Sin veredictos aún.</p>;
  const aria = "Veredictos: " + rows.map((r) => `${r.n} ${r.label}`).join(", ");
  return (
    <ul role="img" aria-label={aria} className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.key} className="flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0 text-zinc-600">{r.label}</span>
          <span className="h-2 flex-1 rounded-full bg-zinc-100">
            <span className={cn("block h-2 rounded-full", r.bar)} style={{ width: `${(r.n / total) * 100}%` }} />
          </span>
          <span className="w-6 shrink-0 text-right font-medium tabular-nums text-zinc-900">{r.n}</span>
        </li>
      ))}
    </ul>
  );
}
