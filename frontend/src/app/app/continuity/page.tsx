"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import {
  emitHandover,
  getContinuity,
  getLatestHandover,
  listContinuityProjects,
} from "@/lib/api/endpoints";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * A dónde se va a ARREGLAR cada dimensión. El índice no es una nota, es un mapa:
 * un número sin salida deja al responsable sabiendo que está mal y sin saber qué hacer.
 */
const DIMENSION_LINK: Record<string, { href: string; cta: string }> = {
  memoria_defectos: { href: "/app/knowledge?tab=propuestas", cta: "Revisar propuestas" },
  razon_etiquetas: { href: "/app/defects", cta: "Etiquetar con su razón" },
  oficio: { href: "/app/knowledge?tab=capturar", cta: "Capturar el oficio" },
  reglas_respaldadas: { href: "/app/knowledge?tab=explorar", cta: "Documentar dominios" },
};

function PageHeader() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Continuidad</h1>
      <p className="text-sm text-zinc-500">
        Si el QA senior se va mañana, ¿cuánto del proyecto queda en Mnemo?
      </p>
    </div>
  );
}

export default function ContinuityPage() {
  const { accessToken } = useAuth();
  const { orgs, activeOrgId, isLoading } = useActiveOrg();
  const [project, setProject] = useState("");

  const isAdmin = useMemo(() => {
    const role = orgs.find((o) => o.id === activeOrgId)?.role;
    return role === "owner" || role === "admin";
  }, [orgs, activeOrgId]);

  const projectsQuery = useQuery({
    queryKey: ["continuity-projects", activeOrgId],
    queryFn: () => listContinuityProjects(accessToken!, activeOrgId),
    enabled: Boolean(accessToken && activeOrgId),
  });
  const projects = projectsQuery.data?.projects ?? [];
  // Estado derivado, sin useEffect: el primer proyecto es el activo hasta que se elija otro.
  const activeProject = project || projects[0] || "";

  const indexQuery = useQuery({
    queryKey: ["continuity", activeOrgId, activeProject],
    queryFn: () => getContinuity(accessToken!, activeOrgId, activeProject),
    enabled: Boolean(accessToken && activeOrgId && activeProject),
  });

  const latestQuery = useQuery({
    queryKey: ["continuity-latest", activeOrgId, activeProject],
    queryFn: () => getLatestHandover(accessToken!, activeOrgId, activeProject),
    enabled: Boolean(accessToken && activeOrgId && activeProject),
    retry: false, // 404 = «aún no hay actas», no un error que reintentar
  });

  const emitMutation = useMutation({
    mutationFn: () => emitHandover(accessToken!, activeOrgId, activeProject),
    onSuccess: () => {
      toast.success("Acta de traspaso emitida y firmada.");
      latestQuery.refetch();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <Skeleton className="h-64 max-w-2xl rounded-xl" />
      </div>
    );
  }

  if (!activeOrgId) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <Card className="max-w-xl p-5">
          <p className="text-sm text-zinc-500">Selecciona una organización.</p>
        </Card>
      </div>
    );
  }

  const idx = indexQuery.data;
  const acta = latestQuery.data;
  const shareUrl = (blob: string) =>
    `${typeof window !== "undefined" ? window.location.origin : ""}/verify#${blob}`;

  return (
    <div className="space-y-8">
      <PageHeader />

      <Card className="max-w-2xl">
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Índice de continuidad</CardTitle>
          {projects.length > 0 && (
            <Select value={activeProject} onValueChange={setProject}>
              <SelectTrigger className="w-[220px]" aria-label="Proyecto">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </CardHeader>
        <CardContent className="space-y-5">
          {projects.length === 0 && !projectsQuery.isLoading ? (
            <p className="text-sm text-zinc-500">
              Todavía no hay proyectos con runs ni conocimiento en esta organización.
            </p>
          ) : idx ? (
            <>
              <div className="flex items-baseline gap-3">
                {idx.score === null ? (
                  <p className="text-sm text-zinc-500">Sin datos suficientes.</p>
                ) : (
                  <>
                    <span className="text-5xl font-semibold tracking-tight text-zinc-900">
                      {idx.score}
                    </span>
                    <span className="text-sm text-zinc-500">
                      / 100 · cuánto de este proyecto sabe Mnemo
                    </span>
                  </>
                )}
              </div>
              <div className="space-y-3">
                {idx.dimensions.map((d) => (
                  <div key={d.key} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-zinc-900">{d.label}</span>
                      <span className="text-zinc-500">
                        {d.den > 0 ? `${d.num} / ${d.den}` : "sin datos"}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-zinc-100">
                      <div
                        className="h-2 rounded-full bg-primary"
                        style={{ width: `${d.ratio === null ? 0 : Math.round(d.ratio * 100)}%` }}
                      />
                    </div>
                    {DIMENSION_LINK[d.key] && d.ratio !== null && d.ratio < 1 && (
                      <Link
                        href={DIMENSION_LINK[d.key].href}
                        className="text-xs font-medium text-primary hover:underline"
                      >
                        {DIMENSION_LINK[d.key].cta} →
                      </Link>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Skeleton className="h-40 rounded-xl" />
          )}
        </CardContent>
      </Card>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="text-base">Acta de traspaso</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-zinc-600">
            Al rotar a un consultor, el acta firma el estado del conocimiento del proyecto:
            el índice, su desglose y el inventario. Verificable por cualquiera con el
            enlace, sin cuenta.
          </p>
          {acta && (
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-sm">
              <p className="text-zinc-900">
                Última acta: <strong>{acta.score ?? "—"}</strong> / 100 ·{" "}
                {new Date(acta.created_at).toLocaleString()}
              </p>
              {acta.share && (
                <button
                  type="button"
                  className="mt-1 text-xs font-medium text-primary hover:underline"
                  onClick={() => {
                    navigator.clipboard.writeText(shareUrl(acta.share));
                    toast.success("Enlace de verificación copiado.");
                  }}
                >
                  Copiar enlace de verificación
                </button>
              )}
            </div>
          )}
          <Button
            disabled={!isAdmin || !activeProject || emitMutation.isPending}
            title={isAdmin ? undefined : "Emitir un acta requiere rol owner/admin"}
            onClick={() => emitMutation.mutate()}
          >
            {emitMutation.isPending ? "Emitiendo…" : "Emitir acta de traspaso"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
