"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import {
  getGithubConfig,
  listRepoTests,
  listKnowledge,
  getGaps,
  listRuns,
  getCalibrationMetrics,
  listKnowledgeProposals,
  getCertificate,
} from "@/lib/api/endpoints";
import { SetupChecklist, type SetupStep } from "@/components/dashboard/SetupChecklist";
import { LatestReleaseHero } from "@/components/dashboard/LatestReleaseHero";
import { Sparkline } from "@/components/dashboard/charts/Sparkline";
import { RadialGauge } from "@/components/dashboard/charts/RadialGauge";
import { VerdictBar } from "@/components/dashboard/charts/VerdictBar";
import { NAV_ITEMS } from "@/components/layout/nav";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import type { ExecutionManifest } from "@/lib/api/types";

const QUICK_ACCESS_HREFS = ["/app/knowledge", "/app/graph", "/app/test-plan"] as const;
const quickAccessItems = NAV_ITEMS.filter((item) =>
  (QUICK_ACCESS_HREFS as readonly string[]).includes(item.href),
);

function KpiError() {
  return <p className="text-sm text-red-500">No se pudo cargar.</p>;
}

function tally(items: (string | null | undefined)[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const it of items) if (it) out[it] = (out[it] ?? 0) + 1;
  return out;
}

function VizCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">{title}</p>
      <div className="flex-1">{children}</div>
    </Card>
  );
}

export default function DashboardPage() {
  const { accessToken } = useAuth();
  const { activeOrgId, isLoading: orgLoading } = useActiveOrg();
  const orgId = activeOrgId || "";
  const enabled = Boolean(accessToken && orgId);
  const opts = { enabled, retry: false } as const;

  const github = useQuery({ queryKey: ["github-config", orgId], queryFn: () => getGithubConfig(accessToken!, { org_id: orgId }), ...opts });
  const repo = useQuery({ queryKey: ["repo-tests", orgId], queryFn: () => listRepoTests(accessToken!, { org_id: orgId }), ...opts });
  const knowledge = useQuery({ queryKey: ["knowledge", orgId], queryFn: () => listKnowledge(accessToken!, orgId), ...opts });
  const gaps = useQuery({ queryKey: ["gaps", orgId, "count"], queryFn: () => getGaps(accessToken!, { org_id: orgId, recommendations: false }), ...opts });
  const runs = useQuery({ queryKey: ["runs", orgId, "dashboard"], queryFn: () => listRuns(accessToken!, orgId, { limit: 20 }), ...opts });
  const calibration = useQuery({ queryKey: ["calibration", orgId], queryFn: () => getCalibrationMetrics(accessToken!, orgId), ...opts });
  const proposals = useQuery({ queryKey: ["knowledge-proposals", orgId], queryFn: () => listKnowledgeProposals(accessToken!, orgId), ...opts });

  const latest = runs.data?.[0];
  // Manifiesto del acta del último run (para el héroe). 404 si no tiene acta → null.
  const cert = useQuery({
    queryKey: ["certificate", latest?.id, "dashboard"],
    queryFn: () => getCertificate(accessToken!, latest!.id),
    enabled: Boolean(accessToken && latest?.id),
    retry: false,
  });

  if (!orgLoading && !orgId) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Panel de control</h1>
        <Card className="p-6">
          <p className="text-sm text-zinc-700">Crea o únete a una organización para empezar.</p>
          <Button asChild className="mt-3"><Link href="/app/org">Ir a Organización</Link></Button>
        </Card>
      </div>
    );
  }

  const steps: SetupStep[] = [
    { n: 1, title: "Conecta GitHub", description: "Enlaza el repositorio de tu equipo.", href: "/app/integrations", cta: "Configurar", done: Boolean(github.data?.configured) },
    { n: 2, title: "Indexa los tests de tu repo", description: "Mnemo aprende el estilo de tus pruebas reales.", href: "/app/integrations", cta: "Indexar", done: (repo.data?.length ?? 0) > 0 },
    { n: 3, title: "Captura conocimiento de QA", description: "Reglas, lecciones y riesgos de tu producto.", href: "/app/knowledge", cta: "Capturar", done: (knowledge.data?.length ?? 0) > 0 },
    { n: 4, title: "Revisa tus gaps de cobertura", description: "Reglas sin un test que las cubra.", href: "/app/graph", cta: "Ver gaps", done: (gaps.data?.length ?? 0) > 0 },
    { n: 5, title: "Genera el test que falta", description: "Desde un gap, al estilo de tu repo, hacia un PR.", href: "/app/graph", cta: "Generar", done: false, highlight: true },
  ];
  const setupComplete = steps.slice(0, 4).every((s) => s.done);
  const checklistLoading = orgLoading || github.isLoading || repo.isLoading || knowledge.isLoading || gaps.isLoading;

  const m = calibration.data;
  const nGapsAlta = (gaps.data ?? []).filter((g) => g.severity === "alta").length;
  const nPending = proposals.data?.length ?? 0;
  const recentRuns = runs.data ?? [];
  const manifest = (cert.data?.canonical_json?.execution_manifest ?? null) as ExecutionManifest | null;

  // Serie de riesgo cronológica (listRuns viene desc), sin nulos.
  const riskSeries = recentRuns.map((r) => r.risk_score).reverse().filter((v): v is number => v != null);
  const verdictCounts = tally(recentRuns.map((r) => r.verdict));
  const accuracy = m && m.total > 0 ? m.accuracy : null;
  const gapsBySeverity = tally((gaps.data ?? []).map((g) => g.severity));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Panel de control</h1>
        <p className="text-sm text-zinc-500">El estado de tu memoria y aseguramiento de QA, de un vistazo.</p>
      </div>

      {/* ── Héroe + precisión ── */}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        {runs.isError ? (
          <Card className="p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">Última release</p>
            <KpiError />
          </Card>
        ) : runs.isLoading ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : latest ? (
          <LatestReleaseHero run={latest} manifest={manifest} />
        ) : (
          <Card className="p-5">
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-400">Última release</p>
            <p className="mt-2 text-sm text-zinc-500">Aún sin runs — sube un reporte en Autopilot.</p>
            <Link href="/app/autopilot" className="mt-3 inline-block text-xs font-medium text-primary hover:underline">Ir a Autopilot →</Link>
          </Card>
        )}
        <VizCard title="Precisión del motor">
          {calibration.isError ? (
            <KpiError />
          ) : calibration.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : accuracy != null ? (
            <div className="space-y-1">
              <RadialGauge value={accuracy} ariaLabel={`Precisión del motor: ${Math.round(accuracy * 100)}%`} />
              <p className="flex items-center gap-1 text-xs text-zinc-400">
                {m!.familias_calibradas} familias calibradas <InfoTooltip term="precision_motor" />
              </p>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Sin calibrar — etiqueta familias en Defect DNA.</p>
          )}
        </VizCard>
      </div>

      {/* ── Tendencia + distribución ── */}
      <div className="grid gap-4 sm:grid-cols-2">
        <VizCard title={`Tendencia de riesgo${riskSeries.length ? ` · últimos ${riskSeries.length}` : ""}`}>
          {runs.isError ? (
            <KpiError />
          ) : runs.isLoading ? (
            <Skeleton className="h-8 w-full" />
          ) : riskSeries.length >= 3 ? (
            <Sparkline values={riskSeries} ariaLabel={`Riesgo: de ${riskSeries[0]} a ${riskSeries[riskSeries.length - 1]} en los últimos ${riskSeries.length} runs`} />
          ) : (
            <p className="text-sm text-zinc-500">Aún pocos runs para una tendencia.</p>
          )}
        </VizCard>
        <VizCard title="Veredictos · últimos 20">
          {runs.isError ? (
            <KpiError />
          ) : runs.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <VerdictBar counts={verdictCounts} />
          )}
        </VizCard>
      </div>

      {/* ── Memoria + gaps ── */}
      <div className="grid gap-4 sm:grid-cols-2">
        <VizCard title="Memoria de QA">
          {knowledge.isError ? (
            <KpiError />
          ) : (
            <>
              <p className="text-3xl font-semibold tracking-tight text-zinc-900">{knowledge.data?.length ?? 0}</p>
              <p className="text-xs text-zinc-400">
                lecciones, reglas y riesgos capturados
                {nPending > 0 && <span className="ml-1 font-medium text-amber-600">· {nPending} propuesta{nPending === 1 ? "" : "s"} de la IA por revisar</span>}
              </p>
            </>
          )}
          <Link href="/app/knowledge" className="mt-1 inline-block text-xs font-medium text-zinc-500 hover:text-zinc-900">Conocimiento →</Link>
        </VizCard>
        <VizCard title="Gaps de cobertura">
          {gaps.isError ? (
            <KpiError />
          ) : (
            <>
              <p className="text-3xl font-semibold tracking-tight text-zinc-900">{gaps.data?.length ?? 0}</p>
              <p className="text-xs text-zinc-400">
                {nGapsAlta > 0 ? <span className="font-medium text-red-600">{nGapsAlta} de severidad alta</span> : "sin severidad alta"}
                {(gapsBySeverity.media ?? 0) > 0 ? ` · ${gapsBySeverity.media} media` : ""}
                {(gapsBySeverity.baja ?? 0) > 0 ? ` · ${gapsBySeverity.baja} baja` : ""}
              </p>
            </>
          )}
          <Link href="/app/graph" className="mt-1 inline-block text-xs font-medium text-zinc-500 hover:text-zinc-900">Ver gaps →</Link>
        </VizCard>
      </div>

      {/* ── Runs recientes (5) ── */}
      {recentRuns.length > 0 && (
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium text-zinc-700">Runs recientes</h3>
            <Link href="/app/autopilot" className="text-xs text-zinc-500 hover:text-zinc-900">Autopilot →</Link>
          </div>
          <ul className="divide-y divide-zinc-100">
            {recentRuns.slice(0, 5).map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0">
                  <span className="font-medium text-zinc-900">{r.project}</span>
                  <span className="ml-2 text-xs text-zinc-400">{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {r.failures > 0 && <Badge>{r.failures} fallos</Badge>}
                  <VerdictBadge verdict={r.verdict} />
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* ── Setup ── */}
      {checklistLoading ? null : setupComplete ? (
        <p className="text-xs text-zinc-400">✓ Configuración completa — GitHub conectado, tests indexados, memoria y gaps activos.</p>
      ) : (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-zinc-700">Pon Mnemo en marcha</h3>
          <SetupChecklist steps={steps} />
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-zinc-700">Accesos rápidos</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          {quickAccessItems.map(({ href, label }) => (
            <Button key={href} asChild variant="outline"><Link href={href}>{label}</Link></Button>
          ))}
        </div>
      </div>
    </div>
  );
}
