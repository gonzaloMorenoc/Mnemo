"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { publishGate } from "@/lib/api/endpoints";
import type { GateResult } from "@/lib/api/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { VerdictBadge } from "@/components/ui/verdict-badge";

const CONCLUSION_STYLE: Record<string, string> = {
  success: "bg-green-100 text-green-700",
  neutral: "bg-zinc-200 text-zinc-700",
  failure: "bg-red-100 text-red-700",
};

const CONCLUSION_LABEL: Record<string, string> = {
  success: "Publicado: OK",
  neutral: "Publicado: neutro",
  failure: "Publicado: bloquea",
};

export function GateCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const [result, setResult] = useState<GateResult | null>(null);
  const publish = useMutation({
    mutationFn: () => publishGate(accessToken!, runId),
    onSuccess: (r) => { setResult(r); toast.success(`Gate: ${r.conclusion}`); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-1 text-sm font-medium text-zinc-700">
          Gate (check run)
          <InfoTooltip term="gate" />
        </h2>
        <Button size="sm" variant="ghost" disabled={publish.isPending} onClick={() => publish.mutate()}>
          {publish.isPending ? "Publicando…" : "Publicar gate"}
        </Button>
      </div>
      {result ? (
        <div className="flex items-center gap-2 text-sm text-zinc-600">
          <Badge className={CONCLUSION_STYLE[result.conclusion] ?? CONCLUSION_STYLE.neutral}>
            {CONCLUSION_LABEL[result.conclusion] ?? result.conclusion}
          </Badge>
          <VerdictBadge verdict={result.verdict} />
          <a className="text-blue-600 underline" href={result.check_run_url} target="_blank" rel="noreferrer">ver check run</a>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">
          Publica el resultado como check en el repositorio de GitHub del proyecto
          (visible en el PR).
        </p>
      )}
    </Card>
  );
}
