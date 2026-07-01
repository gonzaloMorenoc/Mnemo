"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getTriageVerdicts } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

const CATEGORY_STYLE: Record<string, string> = {
  real: "bg-red-100 text-red-700",
  flaky: "bg-amber-100 text-amber-700",
  maintenance: "bg-blue-100 text-blue-700",
  infra: "bg-zinc-200 text-zinc-700",
  unknown: "bg-zinc-100 text-zinc-500",
};

const CATEGORY_LABEL: Record<string, string> = {
  real: "Fallo real",
  flaky: "Flaky",
  maintenance: "Mantenimiento",
  infra: "Infra",
  unknown: "Desconocido",
};

export function TriageVerdictList({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["triage", runId],
    queryFn: () => getTriageVerdicts(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
  });

  if (query.isLoading) return <Skeleton className="h-24 w-full" />;
  if (query.isError) return <Card className="p-5"><p className="text-sm text-red-600">No se pudieron cargar los veredictos.</p></Card>;

  const verdicts = query.data ?? [];
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-medium text-zinc-700">Veredictos de triaje</h2>
        <InfoTooltip term="triaje" />
      </div>
      {/* Leyenda de colores */}
      <div className="flex flex-wrap gap-2 text-xs">
        {Object.entries(CATEGORY_STYLE).map(([cat, cls]) => (
          <span key={cat} className={`rounded-full px-2 py-0.5 font-medium ${cls}`}>
            {CATEGORY_LABEL[cat] ?? cat}
          </span>
        ))}
      </div>
      {verdicts.length === 0 ? (
        <p className="text-sm text-zinc-500">Sin veredictos para este run.</p>
      ) : (
        <ul className="space-y-2">
          {verdicts.map((v) => (
            <li key={v.id} className="flex items-center justify-between text-sm">
              <span className="font-mono text-xs text-zinc-500">{v.failure_id.slice(0, 8)}</span>
              <span className="flex items-center gap-2">
                <Badge className={CATEGORY_STYLE[v.category] ?? CATEGORY_STYLE.unknown}>
                  {CATEGORY_LABEL[v.category] ?? v.category}
                </Badge>
                <span className="text-zinc-500">{(v.confidence * 100).toFixed(0)}%</span>
                <span className="text-zinc-400">{v.rule_applied}</span>
                {v.requires_approval && <Badge className="bg-amber-100 text-amber-700">requiere aprobación</Badge>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
