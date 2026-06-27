"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getBriefing } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function BriefingCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["briefing", runId],
    queryFn: () => getBriefing(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
    retry: false,
  });
  const b = query.data;
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700">Resumen ejecutivo</h2>
        {b && <Badge>{b.verdict}</Badge>}
      </div>
      {b ? (
        <div className="space-y-2 text-sm text-zinc-600">
          <p className="text-zinc-800">{b.summary}</p>
          <p><strong className="text-zinc-900">Recomendación:</strong> {b.recommendation}</p>
          {b.highlights.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5">
              {b.highlights.map((h: string, i: number) => <li key={i}>{h}</li>)}
            </ul>
          )}
        </div>
      ) : (
        <p className="text-sm text-zinc-500">
          {query.isError ? "Resumen no disponible." : "Cargando resumen…"}
        </p>
      )}
    </Card>
  );
}
