"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getDefects, getDefectLineage, getOrganizations, analyzeRootCause } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

function RootCausePanel({ token, defectId }: { token: string; defectId: string }) {
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(regenerate = false) {
    setBusy(true);
    setError(null);
    try {
      const r = await analyzeRootCause(token, defectId, regenerate);
      setText(r.root_cause);
    } catch {
      setError("No se pudo generar el análisis (¿LLM disponible?).");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3">
      <Button onClick={() => run(false)} disabled={busy} className="text-xs">
        {busy ? "Analizando…" : "Analizar causa raíz"}
      </Button>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {text && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-400">Sugerencia generada por IA — revísala.</p>
          <pre className="whitespace-pre-wrap rounded-lg bg-zinc-50 p-3 text-sm text-zinc-700">{text}</pre>
          <Button onClick={() => run(true)} disabled={busy} className="text-xs">Regenerar</Button>
        </div>
      )}
    </div>
  );
}

export default function DefectsPage() {
  const { accessToken } = useAuth();
  const [orgId, setOrgId] = useState<string>("");
  const [selected, setSelected] = useState<string | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });

  const activeOrg = orgId || orgsQuery.data?.[0]?.id || "";

  const defectsQuery = useQuery({
    queryKey: ["defects", activeOrg],
    queryFn: () => getDefects(accessToken!, activeOrg),
    enabled: Boolean(accessToken && activeOrg),
  });

  const lineageQuery = useQuery({
    queryKey: ["lineage", selected],
    queryFn: () => getDefectLineage(accessToken!, selected!),
    enabled: Boolean(accessToken && selected),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Defect DNA</h1>
        <p className="text-sm text-zinc-500">Familias de defecto y su linaje a través de proyectos.</p>
      </div>

      {orgsQuery.data && orgsQuery.data.length > 1 && (
        <select
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          value={activeOrg}
          onChange={(e) => setOrgId(e.target.value)}
        >
          {orgsQuery.data.map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Familias</h2>
          {defectsQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {defectsQuery.isError && (
            <p className="text-sm text-red-600">No se pudieron cargar las familias de defecto.</p>
          )}
          {defectsQuery.data && defectsQuery.data.length === 0 && (
            <p className="text-sm text-zinc-500">No hay familias todavía. Sube un reporte en Assurance.</p>
          )}
          <ul className="space-y-2">
            {defectsQuery.data?.map((f) => (
              <li key={f.id}>
                <button
                  onClick={() => setSelected(f.id)}
                  className="flex w-full items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm hover:bg-zinc-50"
                >
                  <span className="font-medium text-zinc-900">{f.title}</span>
                  <span className="flex items-center gap-2">
                    <Badge>{f.occurrence_count}x</Badge>
                    {f.projects.length > 1 && <Badge>{f.projects.length} proyectos</Badge>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Linaje</h2>
          {!selected && <p className="text-sm text-zinc-500">Selecciona una familia.</p>}
          {lineageQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {lineageQuery.isError && (
            <p className="text-sm text-red-600">No se pudo cargar el linaje de la familia.</p>
          )}
          {lineageQuery.data?.family && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-zinc-900">{lineageQuery.data.family.title}</p>
              <ul className="space-y-1 text-sm text-zinc-600">
                {lineageQuery.data.failures.map((fl) => (
                  <li key={fl.id} className="flex items-center justify-between">
                    <span>{fl.test_name}</span>
                    <Badge>{fl.project}</Badge>
                  </li>
                ))}
              </ul>
              {lineageQuery.data?.family && (
                <RootCausePanel
                  key={lineageQuery.data.family.id}
                  token={accessToken!}
                  defectId={lineageQuery.data.family.id}
                />
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
