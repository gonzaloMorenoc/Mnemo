"use client";

import { usePathname } from "next/navigation";

import { NoOrgState } from "@/components/org/NoOrgState";
import { useActiveOrg } from "@/components/providers/org-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

/** Páginas que tienen sentido sin organización (gestionarla, la guía, verificar, ajustes). */
const PATHS_WITHOUT_ORG: readonly string[] = ["/app/org", "/app/guia", "/app/verify", "/app/settings"];

function OrgsLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className="mx-auto max-w-xl p-5">
      <div className="space-y-3">
        <p role="alert" className="text-sm text-zinc-700">
          No hemos podido cargar tus organizaciones. Si el servidor estaba dormido puede tardar
          hasta un minuto en despertar.
        </p>
        <Button size="sm" variant="outline" onClick={onRetry}>
          Reintentar
        </Button>
      </div>
    </Card>
  );
}

/**
 * Un único punto que decide qué ve quien aún no tiene organización, para que
 * ninguna página tenga que inventarse su propio «Selecciona una organización.».
 */
export function OrgGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { hasNoOrgs, isError, activeOrgId, refetchOrgs } = useActiveOrg();

  if (PATHS_WITHOUT_ORG.some((p) => pathname?.startsWith(p))) return <>{children}</>;
  if (hasNoOrgs) return <NoOrgState />;
  if (isError && !activeOrgId) return <OrgsLoadError onRetry={refetchOrgs} />;
  return <>{children}</>;
}
