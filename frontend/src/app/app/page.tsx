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
} from "@/lib/api/endpoints";
import {
  SetupChecklist,
  type SetupStep,
} from "@/components/dashboard/SetupChecklist";
import { NAV_ITEMS } from "@/components/layout/nav";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

const QUICK_ACCESS_HREFS = ["/app/knowledge", "/app/graph", "/app/test-plan"] as const;
const quickAccessItems = NAV_ITEMS.filter((item) =>
  (QUICK_ACCESS_HREFS as readonly string[]).includes(item.href),
);

function KpiError() {
  return <p className="text-sm text-red-500">No se pudo cargar.</p>;
}

function KpiCard({
  title,
  href,
  cta,
  loading,
  term,
  children,
}: {
  title: string;
  href: string;
  cta: string;
  loading?: boolean;
  term?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <p className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-zinc-400">
        {title}
        {term && <InfoTooltip term={term} />}
      </p>
      {loading ? <Skeleton className="h-10 w-24" /> : <div className="flex-1">{children}</div>}
      <Link href={href} className="text-xs font-medium text-zinc-500 hover:text-zinc-900">
        {cta} →
      </Link>
    </Card>
  );
}

export default function DashboardPage() {
  const { accessToken } = useAuth();
  const { activeOrgId, isLoading: orgLoading } = useActiveOrg();
  const orgId = activeOrgId || "";
  const enabled = Boolean(accessToken && orgId);
  const opts = { enabled, retry: false } as const;

  const github = useQuery({
    queryKey: ["github-config", orgId],
    queryFn: () => getGithubConfig(accessToken!, { org_id: orgId }),
    ...opts,
  });
  const repo = useQuery({
    queryKey: ["repo-tests", orgId],
    queryFn: () => listRepoTests(accessToken!, { org_id: orgId }),
    ...opts,
  });
  const knowledge = useQuery({
    queryKey: ["knowledge", orgId],
    queryFn: () => listKnowledge(accessToken!, orgId),
    ...opts,
  });
  const gaps = useQuery({
    // Solo el conteo → sin recomendaciones LLM (instantáneo)
    queryKey: ["gaps", orgId, "count"],
    queryFn: () => getGaps(accessToken!, { org_id: orgId, recommendations: false }),
    ...opts,
  });
  const runs = useQuery({
    queryKey: ["runs", orgId, "dashboard"],
    queryFn: () => listRuns(accessToken!, orgId, { limit: 5 }),
    ...opts,
  });
  const calibration = useQuery({
    queryKey: ["calibration", orgId],
    queryFn: () => getCalibrationMetrics(accessToken!, orgId),
    ...opts,
  });
  const proposals = useQuery({
    queryKey: ["knowledge-proposals", orgId],
    queryFn: () => listKnowledgeProposals(accessToken!, orgId),
    ...opts,
  });

  if (!orgLoading && !orgId) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Panel de control</h1>
        <Card className="p-6">
          <p className="text-sm text-zinc-700">
            Crea o únete a una organización para empezar.
          </p>
          <Button asChild className="mt-3">
            <Link href="/app/org">Ir a Organización</Link>
          </Button>
        </Card>
      </div>
    );
  }

  const steps: SetupStep[] = [
    {
      n: 1,
      title: "Conecta GitHub",
      description: "Enlaza el repositorio de tu equipo.",
      href: "/app/integrations",
      cta: "Configurar",
      done: Boolean(github.data?.configured),
    },
    {
      n: 2,
      title: "Indexa los tests de tu repo",
      description: "Mnemo aprende el estilo de tus pruebas reales.",
      href: "/app/integrations",
      cta: "Indexar",
      done: (repo.data?.length ?? 0) > 0,
    },
    {
      n: 3,
      title: "Captura conocimiento de QA",
      description: "Reglas, lecciones y riesgos de tu producto.",
      href: "/app/knowledge",
      cta: "Capturar",
      done: (knowledge.data?.length ?? 0) > 0,
    },
    {
      n: 4,
      title: "Revisa tus gaps de cobertura",
      description: "Reglas sin un test que las cubra.",
      href: "/app/graph",
      cta: "Ver gaps",
      done: (gaps.data?.length ?? 0) > 0,
    },
    {
      n: 5,
      title: "Genera el test que falta",
      description: "Desde un gap, al estilo de tu repo, hacia un PR.",
      href: "/app/graph",
      cta: "Generar",
      done: false,
      highlight: true,
    },
  ];
  const setupComplete = steps.slice(0, 4).every((s) => s.done);

  const latest = runs.data?.[0];
  const m = calibration.data;
  const nGapsAlta = (gaps.data ?? []).filter((g) => g.severity === "alta").length;
  const nPending = proposals.data?.length ?? 0;

  const checklistLoading =
    orgLoading || github.isLoading || repo.isLoading || knowledge.isLoading || gaps.isLoading;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          Panel de control
        </h1>
        <p className="text-sm text-zinc-500">
          El estado de tu memoria y aseguramiento de QA, de un vistazo.
        </p>
      </div>

      {/* ── KPIs ── */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard title="Último run" href="/app/autopilot" cta="Ver runs" loading={runs.isLoading}>
          {runs.isError ? (
            <KpiError />
          ) : latest ? (
            <div className="space-y-1">
              <VerdictBadge verdict={latest.verdict} />
              <p className="truncate text-sm font-medium text-zinc-900">{latest.project}</p>
              <p className="text-xs text-zinc-400">
                {latest.created_at ? new Date(latest.created_at).toLocaleString() : ""}
                {latest.failures > 0 ? ` · ${latest.failures} fallos` : ""}
              </p>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Aún sin runs — sube un reporte en Autopilot.</p>
          )}
        </KpiCard>

        <KpiCard title="Precisión del motor" term="precision_motor" href="/app/calibration" cta="Calibración" loading={calibration.isLoading}>
          {calibration.isError ? (
            <KpiError />
          ) : m && m.total > 0 ? (
            <div className="space-y-1">
              <p className="text-3xl font-semibold tracking-tight text-zinc-900">
                {(m.accuracy * 100).toFixed(0)}%
              </p>
              <p className="text-xs text-zinc-400">{m.familias_calibradas} familias calibradas</p>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Sin calibrar aún — etiqueta familias en Defect DNA.</p>
          )}
        </KpiCard>

        <KpiCard title="Memoria de QA" href="/app/knowledge" cta="Conocimiento" loading={knowledge.isLoading}>
          <div className="space-y-1">
            <p className="text-3xl font-semibold tracking-tight text-zinc-900">
              {knowledge.data?.length ?? 0}
            </p>
            <p className="text-xs text-zinc-400">
              lecciones, reglas y riesgos capturados
              {nPending > 0 && (
                <span className="ml-1 font-medium text-amber-600">
                  · {nPending} propuesta{nPending === 1 ? "" : "s"} de la IA por revisar
                </span>
              )}
            </p>
          </div>
        </KpiCard>

        <KpiCard title="Gaps de cobertura" term="regla_sin_test" href="/app/graph" cta="Ver gaps" loading={gaps.isLoading}>
          <div className="space-y-1">
            <p className="text-3xl font-semibold tracking-tight text-zinc-900">
              {gaps.data?.length ?? 0}
            </p>
            <p className="text-xs text-zinc-400">
              {nGapsAlta > 0 ? (
                <span className="font-medium text-red-600">{nGapsAlta} de severidad alta</span>
              ) : (
                "sin severidad alta"
              )}
            </p>
          </div>
        </KpiCard>
      </div>

      {/* ── Runs recientes ── */}
      {(runs.data?.length ?? 0) > 0 && (
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium text-zinc-700">Runs recientes</h3>
            <Link href="/app/autopilot" className="text-xs text-zinc-500 hover:text-zinc-900">
              Autopilot →
            </Link>
          </div>
          <ul className="divide-y divide-zinc-100">
            {runs.data!.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0">
                  <span className="font-medium text-zinc-900">{r.project}</span>
                  <span className="ml-2 text-xs text-zinc-400">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
                  </span>
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

      {/* ── Setup: checklist solo mientras esté incompleto. NO decidir hasta que
          las queries carguen: si no, en cada carga fría el bloque aparecía con
          skeletons y desaparecía de golpe (parpadeo + salto de layout). ── */}
      {checklistLoading ? null : setupComplete ? (
        <p className="text-xs text-zinc-400">
          ✓ Configuración completa — GitHub conectado, tests indexados, memoria y gaps activos.
        </p>
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
          <Button key={href} asChild variant="outline">
            <Link href={href}>{label}</Link>
          </Button>
        ))}
      </div>
      </div>
    </div>
  );
}
