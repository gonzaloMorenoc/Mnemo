import Link from "next/link";

import type { ExecutionManifest, RunListItem } from "@/lib/api/types";
import { Card } from "@/components/ui/card";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import { RiskMeter } from "@/components/dashboard/charts/RiskMeter";

export function LatestReleaseHero({
  run,
  manifest,
  certified,
}: {
  run: RunListItem;
  manifest: ExecutionManifest | null;
  certified: boolean;
}) {
  // El riesgo no aplica en sin_confirmar (o si el run no trae score) → "—", no 0.
  const riskScore = run.verdict === "sin_confirmar" || run.risk_score == null ? null : run.risk_score;
  return (
    <Card className="p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">Última release</p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <span className="text-base"><VerdictBadge verdict={run.verdict} /></span>
        {certified && (
          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
            acta firmada ✓
          </span>
        )}
      </div>
      <p className="mt-2 text-lg font-semibold tracking-tight text-zinc-900">{run.project}</p>
      <div className="mt-2">
        <RiskMeter score={riskScore} />
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        {manifest
          ? `${manifest.total} tests · ${manifest.passed} ✓ · ${manifest.failed} ✗`
          : `${run.failures} fallo${run.failures === 1 ? "" : "s"}`}
        {run.commit_sha ? ` · commit ${run.commit_sha.slice(0, 8)}` : ""}
        {run.created_at ? ` · ${new Date(run.created_at).toLocaleString()}` : ""}
      </p>
      <Link href="/app/autopilot" className="mt-3 inline-block text-xs font-medium text-primary hover:underline">
        Ver run →
      </Link>
    </Card>
  );
}
