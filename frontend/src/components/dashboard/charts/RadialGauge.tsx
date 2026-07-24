const R = 34;
const CX = 40;
const CY = 40;
const STROKE = 8;
const ARC = Math.PI * R; // longitud del semicírculo

/** Gauge semicircular 0..1 con el porcentaje en el centro. */
export function RadialGauge({ value, ariaLabel }: { value: number; ariaLabel: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const dash = (pct / 100) * ARC;
  const d = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`;
  return (
    <svg role="img" aria-label={ariaLabel} viewBox="0 0 80 48" className="w-full max-w-[168px]">
      <path d={d} fill="none" strokeWidth={STROKE} strokeLinecap="round" className="stroke-zinc-200" />
      <path d={d} fill="none" strokeWidth={STROKE} strokeLinecap="round" strokeDasharray={`${dash} ${ARC}`} className="stroke-primary" />
      <text x={CX} y={CY - 6} textAnchor="middle" className="fill-zinc-900 text-[15px] font-semibold">{pct}%</text>
    </svg>
  );
}
