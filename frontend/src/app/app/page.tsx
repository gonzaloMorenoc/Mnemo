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
} from "@/lib/api/endpoints";
import {
  SetupChecklist,
  type SetupStep,
} from "@/components/dashboard/SetupChecklist";
import { NAV_ITEMS } from "@/components/layout/nav";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const QUICK_ACCESS_HREFS = ["/app/knowledge", "/app/graph", "/app/test-plan"] as const;
const quickAccessItems = NAV_ITEMS.filter((item) =>
  (QUICK_ACCESS_HREFS as readonly string[]).includes(item.href),
);

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
    queryKey: ["gaps", orgId],
    queryFn: () => getGaps(accessToken!, { org_id: orgId }),
    ...opts,
  });

  if (!orgLoading && !orgId) {
    return (
      <Card className="p-6">
        <p className="text-sm text-zinc-700">
          Crea o únete a una organización para empezar.
        </p>
        <Button asChild className="mt-3">
          <Link href="/app/org">Ir a Organización</Link>
        </Button>
      </Card>
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

  const loading =
    orgLoading ||
    github.isLoading ||
    repo.isLoading ||
    knowledge.isLoading ||
    gaps.isLoading;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900">
          Pon Mnemo en marcha
        </h2>
        <p className="text-sm text-zinc-500">
          Sigue estos pasos para poner en marcha tu memoria de QA.
        </p>
      </div>
      <SetupChecklist steps={steps} loading={loading} />
      <div className="grid gap-3 sm:grid-cols-3">
        {quickAccessItems.map(({ href, label }) => (
          <Button key={href} asChild variant="outline">
            <Link href={href}>{label}</Link>
          </Button>
        ))}
      </div>
    </div>
  );
}
