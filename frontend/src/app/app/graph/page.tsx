"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Network } from "lucide-react";

import Link from "next/link";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { getGraph, getGaps, getKnowledgeItem, generatePlaywrightTest, openAutomationPr } from "@/lib/api/endpoints";
import type { AutoGenCase, CoverageGap, GeneratedTest, Graph } from "@/lib/api/types";
import { KnowledgeGraphView } from "@/components/graph/knowledge-graph-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

// ─── gap kind labels ──────────────────────────────────────────────────────────

const GAP_KIND_LABEL: Record<string, string> = {
  regla_sin_test: "Regla sin test",
  repo_no_indexado: "Repo sin indexar",
  defecto_sin_conocimiento: "Defecto sin conocimiento",
  dominio_sin_leccion: "Dominio sin lección",
  riesgo_sin_mitigacion: "Riesgo sin mitigación",
};

// ─── severity labels ──────────────────────────────────────────────────────────

const SEVERITY_LABEL: Record<CoverageGap["severity"], string> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
};

// ─── severity ordering ────────────────────────────────────────────────────────

const SEVERITY_ORDER: Record<CoverageGap["severity"], number> = {
  alta: 0,
  media: 1,
  baja: 2,
};

function sortGaps(gaps: CoverageGap[]): CoverageGap[] {
  return [...gaps].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );
}

// ─── severity badge variant ───────────────────────────────────────────────────

function severityClass(severity: CoverageGap["severity"]): string {
  if (severity === "alta") return "bg-red-100 text-red-700 border-red-200";
  if (severity === "media") return "bg-amber-100 text-amber-700 border-amber-200";
  return "bg-zinc-100 text-zinc-600 border-zinc-200";
}

// ─── GapTestSection ───────────────────────────────────────────────────────────

function GapTestSection({ gap, accessToken, activeOrgId }: {
  gap: CoverageGap; accessToken: string; activeOrgId: string;
}) {
  const [result, setResult] = useState<GeneratedTest | null>(null);
  const genMut = useMutation({
    mutationFn: async () => {
      const item = await getKnowledgeItem(accessToken, { org_id: activeOrgId, id: gap.affected[0] });
      const steps = [item.challenge, item.approach, item.outcome].filter(Boolean) as string[];
      const autoCase: AutoGenCase = { title: item.title, steps };
      return generatePlaywrightTest(accessToken, {
        case: autoCase,
        org_id: activeOrgId,
      });
    },
    onSuccess: (r) => setResult(r),
    onError: () => toast.error("No se pudo generar el test"),
  });
  const prMut = useMutation({
    mutationFn: () => openAutomationPr(accessToken, {
      org_id: activeOrgId, code: result!.code, filename: result!.filename,
    }),
    onSuccess: (r) => toast.success(`PR abierto: ${r.pr_url}`),
    onError: () => toast.error("No se pudo abrir el PR"),
  });
  return (
    <div className="mt-2">
      <Button size="sm" variant="outline" disabled={genMut.isPending}
        onClick={() => genMut.mutate()} data-testid={`gap-generate-${gap.affected[0]}`}>
        {genMut.isPending ? "Generando…" : "Generar test"}
      </Button>
      {result && (
        <div className="mt-2">
          <pre className="rounded bg-zinc-900 text-zinc-100 p-3 text-xs overflow-x-auto whitespace-pre-wrap">{result.code}</pre>
          <Button size="sm" className="mt-2" disabled={prMut.isPending} onClick={() => prMut.mutate()}>
            {prMut.isPending ? "Abriendo PR…" : "Abrir draft PR"}
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── empty graph ──────────────────────────────────────────────────────────────

const EMPTY_GRAPH: Graph = { nodes: [], edges: [] };

// ─── page ─────────────────────────────────────────────────────────────────────

export default function GraphPage() {
  const { accessToken } = useAuth();
  const { activeOrgId, isLoading } = useActiveOrg();

  const graphQuery = useQuery({
    queryKey: ["graph", activeOrgId],
    queryFn: () => getGraph(accessToken!, { org_id: activeOrgId! }),
    enabled: !!accessToken && !!activeOrgId,
  });

  const gapsQuery = useQuery({
    queryKey: ["graph-gaps", activeOrgId],
    queryFn: () => getGaps(accessToken!, { org_id: activeOrgId! }),
    enabled: !!accessToken && !!activeOrgId,
  });

  // Degrade on errors — toast once (not on every re-render)
  useEffect(() => {
    if (graphQuery.isError) {
      toast.error((graphQuery.error as Error).message ?? "Error al cargar el grafo");
    }
  }, [graphQuery.isError, graphQuery.error]);

  useEffect(() => {
    if (gapsQuery.isError) {
      toast.error((gapsQuery.error as Error).message ?? "Error al cargar los gaps");
    }
  }, [gapsQuery.isError, gapsQuery.error]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader />
        <p className="text-sm text-zinc-500">Cargando…</p>
      </div>
    );
  }

  if (!activeOrgId && !isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader />
        <Card className="max-w-xl p-5">
          <p className="text-sm text-zinc-500">
            Selecciona una organización para ver el Knowledge Graph.
          </p>
        </Card>
      </div>
    );
  }

  const graph = graphQuery.data ?? EMPTY_GRAPH;
  const gaps = gapsQuery.data ?? [];
  const sortedGaps = sortGaps(gaps);
  const noKnowledge = !graphQuery.isLoading && graph.nodes.length === 0;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 overflow-hidden">
      <PageHeader />

      <div className="flex min-h-0 flex-1 gap-4">
        {/* ── left: react-flow graph ── */}
        <div className="relative min-h-0 flex-1 rounded-2xl border border-zinc-200 bg-white shadow-sm">
          {noKnowledge ? (
            <div className="flex h-full flex-col items-center justify-center gap-3">
              <p className="text-sm text-zinc-400">
                Aún no hay conocimiento suficiente
              </p>
              <Button asChild variant="outline" size="sm">
                <Link href="/app/knowledge">Captura conocimiento</Link>
              </Button>
            </div>
          ) : (
            <div className="h-full w-full" data-testid="graph-view-container">
              <KnowledgeGraphView graph={graph} />
            </div>
          )}
        </div>

        {/* ── right: coverage gaps panel ── */}
        <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-y-auto xl:w-96">
          <div className="flex items-center gap-2">
            <Network size={16} className="text-zinc-400" />
            <h2 className="flex items-center gap-1 text-sm font-semibold text-zinc-700">
              Coverage Gaps
              <InfoTooltip term="regla_sin_test" label="Qué es: Coverage Gap" />
            </h2>
            {sortedGaps.length > 0 && (
              <span className="ml-auto rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500">
                {sortedGaps.length}
              </span>
            )}
          </div>

          {gapsQuery.isLoading && (
            <p className="text-xs text-zinc-400">Cargando gaps…</p>
          )}

          {!gapsQuery.isLoading && sortedGaps.length === 0 && (
            <Card className="p-4">
              <p className="text-xs text-zinc-500">
                No se detectaron gaps de cobertura.
              </p>
            </Card>
          )}

          {sortedGaps.map((gap) => (
            <Card key={`${gap.kind}-${gap.title}`} className="p-4">
              <div className="mb-2 flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${severityClass(gap.severity)}`}
                  data-testid={`gap-severity-${gap.severity}`}
                >
                  {SEVERITY_LABEL[gap.severity] ?? gap.severity}
                </span>
                <span className="truncate text-sm font-medium text-zinc-800">
                  {gap.title}
                </span>
              </div>
              <span
                className="mb-2 inline-block text-xs text-zinc-500"
                data-testid={`gap-kind-${gap.kind}`}
              >
                {GAP_KIND_LABEL[gap.kind] ?? gap.kind}
              </span>
              <p className="mb-2 text-xs text-zinc-600">{gap.recommendation}</p>
              {gap.kind === "regla_sin_test" && gap.affected.length > 0 && accessToken && activeOrgId && (
                <GapTestSection gap={gap} accessToken={accessToken} activeOrgId={activeOrgId} />
              )}
              {gap.affected.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {gap.affected.map((a) => (
                    <Badge key={a} className="text-xs">
                      {a}
                    </Badge>
                  ))}
                  <span className="text-xs text-zinc-400">
                    ({gap.affected.length} afectados)
                  </span>
                </div>
              )}
            </Card>
          ))}
        </aside>
      </div>
    </div>
  );
}

function PageHeader() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
        Knowledge Graph
      </h1>
      <p className="text-sm text-zinc-500">
        Mapa de conocimiento, dominios y gaps de cobertura del equipo de QA.
      </p>
    </div>
  );
}
