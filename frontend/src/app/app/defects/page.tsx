"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { getDefects, getDefectLineage, analyzeRootCause } from "@/lib/api/endpoints";
import { BookOpen, Dna } from "lucide-react";

import { FamilyLabelControl } from "@/components/autopilot/FamilyLabelControl";
import { FamilyMemoryPanel } from "@/components/defects/FamilyMemoryPanel";
import { CategoryBadge } from "@/components/ui/category-badge";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

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
      <div className="flex items-center gap-1">
        <Button onClick={() => run(false)} disabled={busy} className="text-xs">
          {busy ? "Analizando…" : "Analizar causa raíz"}
        </Button>
        <InfoTooltip content="Usa el LLM; puede tardar unos segundos." label="Ayuda: Analizar causa raíz" />
      </div>
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
  const { activeOrgId } = useActiveOrg();
  const [selected, setSelected] = useState<string | null>(null);

  const defectsQuery = useQuery({
    queryKey: ["defects", activeOrgId],
    queryFn: () => getDefects(accessToken!, activeOrgId),
    enabled: Boolean(accessToken && activeOrgId),
  });

  const lineageQuery = useQuery({
    queryKey: ["lineage", selected],
    queryFn: () => getDefectLineage(accessToken!, selected!),
    enabled: Boolean(accessToken && selected),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-zinc-900">
          Defect DNA
          <InfoTooltip term="defecto_sin_conocimiento" label="Qué es: Defect DNA" />
        </h1>
        <p className="text-sm text-zinc-500">Familias de defecto y su linaje a través de proyectos.</p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Familias</h2>
          {defectsQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {defectsQuery.isError && (
            <p className="text-sm text-red-600">No se pudieron cargar las familias de defecto.</p>
          )}
          {defectsQuery.data && defectsQuery.data.length === 0 && (
            <EmptyState
              icon={Dna}
              title="Aún no hay familias de fallos"
              description="Cuando analices un run, Mnemo agrupará los fallos parecidos en familias y las verás aquí con su etiqueta y su lección."
              actionHref="/app/autopilot"
              actionLabel="Analizar un run"
            />
          )}
          <ul className="space-y-2">
            {defectsQuery.data?.map((f) => (
              <li key={f.id}>
                <button
                  onClick={() => setSelected(f.id)}
                  className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm hover:bg-zinc-50"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate font-medium text-zinc-900">{f.title}</span>
                      {f.has_lesson && (
                        <BookOpen
                          size={13}
                          className="shrink-0 text-emerald-600"
                          aria-label="Tiene lección en la memoria"
                        />
                      )}
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {f.label && f.label !== "unknown" && <CategoryBadge category={f.label} />}
                      <Badge>{f.occurrence_count}x</Badge>
                    </span>
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-zinc-400">
                    {f.projects.slice(0, 3).map((p) => (
                      <Badge key={p} className="border-blue-200 bg-blue-50 text-blue-700">{p}</Badge>
                    ))}
                    {f.last_seen && <span>visto {f.last_seen.slice(0, 10)}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-4">
          <h2 className="mb-3 flex items-center gap-1 text-sm font-medium text-zinc-700">
            Linaje
            <InfoTooltip term="linaje" label="Qué es: Linaje de defecto" />
          </h2>
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
                <FamilyMemoryPanel
                  key={`mem-${lineageQuery.data.family.id}`}
                  token={accessToken!}
                  orgId={activeOrgId}
                  familyId={lineageQuery.data.family.id}
                />
              )}
              {lineageQuery.data?.family && (
                <RootCausePanel
                  key={lineageQuery.data.family.id}
                  token={accessToken!}
                  defectId={lineageQuery.data.family.id}
                />
              )}
              {lineageQuery.data?.family && (
                <FamilyLabelControl key={`label-${lineageQuery.data.family.id}`} familyId={lineageQuery.data.family.id} />
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
