"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { getCalibrationMetrics } from "@/lib/api/endpoints";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function CalibrationPage() {
  const { accessToken } = useAuth();
  const { activeOrgId } = useActiveOrg();

  const metricsQuery = useQuery({
    queryKey: ["calibration", activeOrgId],
    queryFn: () => getCalibrationMetrics(accessToken!, activeOrgId),
    enabled: Boolean(accessToken && activeOrgId),
  });

  const m = metricsQuery.data;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Calibración</h1>
        <p className="text-sm text-zinc-500">Precisión del motor de triaje con tus correcciones (el foso).</p>
      </div>

      {metricsQuery.isLoading && <Skeleton className="h-40 w-full max-w-xl" />}
      {metricsQuery.isError && (
        <Card className="max-w-xl p-5"><p className="text-sm text-red-600">No se pudieron cargar las métricas.</p></Card>
      )}
      {m && m.total === 0 && (
        <Card className="max-w-xl p-5 space-y-3">
          <p className="text-sm text-zinc-500">
            Aún no hay correcciones. Etiqueta familias en Defect DNA para calibrar el motor.
          </p>
          <Button asChild variant="outline" size="sm">
            <Link href="/app/defects">Ir a Defect DNA</Link>
          </Button>
        </Card>
      )}
      {m && m.total > 0 && (
        <Card className="max-w-xl space-y-4 p-6">
          <div>
            <p className="text-5xl font-semibold tracking-tight text-zinc-900">{(m.accuracy * 100).toFixed(0)}%</p>
            <p className="text-sm text-zinc-500">precisión del motor ({m.aciertos}/{m.total} correcciones coincidieron)</p>
          </div>
          <p className="text-sm text-zinc-600">{m.familias_calibradas} familias calibradas</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(m.por_categoria ?? {}).map(([cat, n]) => (
              <Badge key={cat}>{cat}: {n}</Badge>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
