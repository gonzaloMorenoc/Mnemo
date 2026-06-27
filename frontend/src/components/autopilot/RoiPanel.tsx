"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getTriageVerdicts } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";

const MIN_POR_FALLO = 15;

export function RoiPanel({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["triage", runId],
    queryFn: () => getTriageVerdicts(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
    retry: false,
  });
  const verdicts = query.data ?? [];
  const autoTriados = verdicts.filter((v) => !v.requires_approval && v.category !== "unknown").length;
  const horas = ((autoTriados * MIN_POR_FALLO) / 60).toFixed(1);
  return (
    <Card className="space-y-2 p-5">
      <h2 className="text-sm font-medium text-zinc-700">Retorno (ROI)</h2>
      <div className="flex gap-6 text-sm text-zinc-600">
        <span><strong className="text-zinc-900">{autoTriados}</strong> auto-triados</span>
        <span><strong className="text-zinc-900">{horas} h</strong> ahorradas</span>
        <span><strong className="text-zinc-900">0 €</strong> / release</span>
      </div>
      <p className="text-xs text-zinc-400">
        Supuesto: 15 min de triaje manual por fallo. Modelo ejecutado en local — coste de API nulo.
      </p>
    </Card>
  );
}
