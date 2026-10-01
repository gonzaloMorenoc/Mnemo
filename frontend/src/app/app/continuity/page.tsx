"use client";

import { useLayoutEffect, useMemo, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { buildShareUrl } from "@/lib/certificate-share";
import { continuityBand, deltaDesdeActa } from "@/lib/continuity-band";
import { fechaActa } from "@/lib/acta-format";
import { RotationRiskMap } from "@/components/continuity/RotationRiskMap";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

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
  // Enlace directo a un proyecto (?project=checkout-suite): sin él, la vista abre en
  // el primero por orden alfabético. window.location en vez de useSearchParams para
  // no forzar Suspense (mismo patrón que /app/knowledge?tab=).
  useLayoutEffect(() => {
    const p = new URLSearchParams(window.location.search).get("project");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (p) setProject(p);
  }, []);
  const [enlaceManual, setEnlaceManual] = useState<string | null>(null);
  // Quién se va y quién llega: van FIRMADOS dentro del acta (opcionales).
  const [de, setDe] = useState("");
  const [para, setPara] = useState("");

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
  // Estado derivado, sin useEffect: el elegido (si existe en la org) o el primero.
  const activeProject = projects.includes(project) ? project : projects[0] || "";

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
    mutationFn: () => emitHandover(accessToken!, activeOrgId, activeProject, de.trim(), para.trim()),
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

  // El proyecto elegido viaja en la URL: sobrevive a una recarga y se puede compartir.
  function elegirProyecto(p: string) {
    setProject(p);
    setEnlaceManual(null);
    window.history.replaceState(null, "", `?project=${encodeURIComponent(p)}`);
  }

  // Con el prefijo que /verify exige (#v1.): sin él, el enlace abría el formulario
  // vacío, sin sello ni error. Si el portapapeles falla (contexto no seguro, permiso),
  // el enlace queda a la vista para copiarlo a mano — nunca un «copiado» falso.
  async function copyShareLink(share: string) {
    const url = buildShareUrl(window.location.origin, share);
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Enlace de verificación copiado.");
    } catch {
      setEnlaceManual(url);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader />

      {projectsQuery.isError ? (
        // Un 502 o una sesión caducada NO es «no hay proyectos»: disfrazar el
        // error de vacío manda al usuario a sembrar datos que ya existen.
        <Card className="max-w-3xl p-5">
          <div className="space-y-2">
            <p role="alert" className="text-sm text-red-700">
              No se pudo cargar la continuidad.{" "}
              {projectsQuery.error instanceof Error ? projectsQuery.error.message : ""}
            </p>
            <Button size="sm" variant="outline" onClick={() => projectsQuery.refetch()}>
              Reintentar
            </Button>
          </div>
        </Card>
      ) : projects.length === 0 && !projectsQuery.isPending ? (
        <Card className="max-w-3xl p-5">
          <p className="text-sm text-zinc-500">
            Todavía no hay proyectos con ejecuciones ni conocimiento en esta organización.
          </p>
        </Card>
      ) : (
        <>
          <Card className="max-w-3xl">
            <CardHeader>
              <CardTitle className="text-base">Riesgo de rotación por proyecto</CardTitle>
              <p className="text-sm text-zinc-500">
                Del proyecto más expuesto al más cubierto. Pulsa uno para ver qué le falta.
              </p>
            </CardHeader>
            <CardContent>
              {accessToken && (
                <RotationRiskMap
                  accessToken={accessToken}
                  orgId={activeOrgId}
                  activeProject={activeProject}
                  onSelect={elegirProyecto}
                />
              )}
            </CardContent>
          </Card>

          <Card className="max-w-3xl">
            <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
              <CardTitle className="text-base">
                Índice de continuidad{activeProject ? ` · ${activeProject}` : ""}
              </CardTitle>
              {idx && (
                <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${continuityBand(idx.score).chip}`}>
                  {continuityBand(idx.score).label}
                </span>
              )}
            </CardHeader>
            <CardContent className="space-y-5">
              {indexQuery.isError ? (
                <div className="space-y-2">
                  <p role="alert" className="text-sm text-red-700">No se pudo calcular el índice de este proyecto.</p>
                  <Button size="sm" variant="outline" onClick={() => indexQuery.refetch()}>
                    Reintentar
                  </Button>
                </div>
              ) : idx ? (
                <>
                  <div className="space-y-1">
                    {idx.score === null ? (
                      <p className="text-sm text-zinc-500">Sin datos suficientes.</p>
                    ) : (
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className={`text-5xl font-semibold tracking-tight tabular-nums ${continuityBand(idx.score).text}`}>
                          {idx.score}
                        </span>
                        <span className="text-sm text-zinc-500">/ 100 · cuánto de este proyecto sabe Mnemo</span>
                        {deltaDesdeActa(idx.score, acta?.score ?? null) && (
                          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700">
                            {deltaDesdeActa(idx.score, acta?.score ?? null)}
                          </span>
                        )}
                      </div>
                    )}
                    <p className="text-sm font-medium text-zinc-800">{continuityBand(idx.score).headline}</p>
                  </div>
                  <div className="space-y-3">
                    {idx.dimensions.map((d) => {
                      const medible = d.ratio !== null;
                      const banda = continuityBand(medible ? Math.round(d.ratio! * 100) : null);
                      return (
                        <div key={d.key} className="space-y-1">
                          <div className="flex items-center justify-between gap-2 text-sm">
                            <span className={medible ? "font-medium text-zinc-900" : "font-medium text-zinc-500"}>
                              {d.label}
                            </span>
                            <span className="text-zinc-500">
                              {medible ? `${d.num} / ${d.den}` : "sin datos · no cuenta en el índice"}
                            </span>
                          </div>
                          {medible && (
                            <div className="h-2 rounded-full bg-zinc-100">
                              <div
                                className={`h-2 rounded-full ${banda.bar}`}
                                style={{ width: `${Math.round(d.ratio! * 100)}%` }}
                              />
                            </div>
                          )}
                          {DIMENSION_LINK[d.key] && medible && d.ratio! < 1 && (
                            <Link
                              href={DIMENSION_LINK[d.key].href}
                              className="text-xs font-medium text-primary hover:underline"
                            >
                              {DIMENSION_LINK[d.key].cta} →
                            </Link>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <Skeleton className="h-40 rounded-xl" />
              )}
            </CardContent>
          </Card>
        </>
      )}

      <Card className="max-w-3xl">
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
                {fechaActa(acta.created_at)}
              </p>
              {acta.integridad && (
                acta.integridad.intacto ? (
                  <p className="mt-1 text-xs font-medium text-emerald-700">
                    ✓ Lo depositado sigue intacto: {acta.integridad.n_acta} elementos, la misma huella que firma el acta.
                  </p>
                ) : (
                  <p role="alert" className="mt-1 text-xs font-medium text-amber-800">
                    ⚠ El conocimiento ha cambiado desde el acta ({acta.integridad.n_acta} → {acta.integridad.n_actual ?? "—"} elementos):
                    su huella ya no coincide con la firmada. Emite una nueva si el cambio es legítimo.
                  </p>
                )
              )}
              {acta.share && (
                <div className="mt-2 space-y-2">
                  <Button size="sm" variant="outline" onClick={() => copyShareLink(acta.share)}>
                    Copiar enlace de verificación
                  </Button>
                  {enlaceManual && (
                    <input
                      readOnly
                      value={enlaceManual}
                      aria-label="Enlace de verificación"
                      onFocus={(e) => e.currentTarget.select()}
                      className="w-full rounded border border-zinc-200 px-2 py-1 font-mono text-xs text-zinc-600"
                    />
                  )}
                </div>
              )}
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="font-medium text-zinc-700">Quién se va</span>
              <Input value={de} onChange={(e) => setDe(e.target.value)} maxLength={120}
                     placeholder="p. ej. María (QA senior)" aria-label="Quién se va" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="font-medium text-zinc-700">Quién llega</span>
              <Input value={para} onChange={(e) => setPara(e.target.value)} maxLength={120}
                     placeholder="p. ej. Pablo" aria-label="Quién llega" />
            </label>
          </div>
          <Button
            disabled={!isAdmin || !activeProject || emitMutation.isPending}
            onClick={() => emitMutation.mutate()}
          >
            {emitMutation.isPending ? "Emitiendo…" : "Emitir acta de traspaso"}
          </Button>
          {!isAdmin && (
            <p className="text-xs text-zinc-500">
              Solo un administrador de la organización puede emitir el acta.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
