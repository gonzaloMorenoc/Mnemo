"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getTriageVerdicts } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { CATEGORY_LABEL, CATEGORY_STYLE, CategoryBadge } from "@/components/ui/category-badge";

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
      <p className="text-xs text-zinc-400">Paso 1 — qué dice el motor de cada fallo.</p>
      {/* Leyenda de colores (paleta única de category-badge: el color ES información) */}
      <div className="flex flex-wrap gap-2 text-xs">
        {Object.keys(CATEGORY_STYLE).map((cat) => (
          <span key={cat} className={`rounded-full px-2 py-0.5 font-medium ${CATEGORY_STYLE[cat]}`}>
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
              <span className="font-mono text-xs text-zinc-500">fallo {v.failure_id.slice(0, 8)}</span>
              <span className="flex items-center gap-2">
                <CategoryBadge category={v.category} />
                <span className="text-zinc-500">confianza {(v.confidence * 100).toFixed(0)}%</span>
                <span className="text-zinc-400">regla: {v.rule_applied}</span>
                {v.requires_approval && <Badge className="bg-amber-100 text-amber-700">requiere aprobación</Badge>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
