"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";
import { getContinuity, listContinuityProjects } from "@/lib/api/endpoints";
import { continuityBand } from "@/lib/continuity-band";
import { cn } from "@/lib/utils";

/**
 * Todos los proyectos de la organización en una sola vista, del más expuesto a
 * una rotación al más cubierto. Es la respuesta a «¿qué proyecto me preocupa si
 * mañana rota alguien?», que con un selector exigía ir proyecto a proyecto.
 */
export function RotationRiskMap({
  accessToken,
  orgId,
  activeProject,
  onSelect,
  hrefFor,
  limit,
}: {
  accessToken: string;
  orgId: string;
  activeProject?: string;
  onSelect?: (project: string) => void;
  /** Si se da, cada fila es un ENLACE (navegar a otra página) en vez de un botón. */
  hrefFor?: (project: string) => string;
  /** Muestra solo los N más expuestos (el resumen del Dashboard). */
  limit?: number;
}) {
  const projectsQuery = useQuery({
    queryKey: ["continuity-projects", orgId],
    queryFn: () => listContinuityProjects(accessToken, orgId),
    enabled: Boolean(accessToken && orgId),
  });
  const projects = projectsQuery.data?.projects ?? [];

  // Una consulta por proyecto, con la MISMA clave que la vista de detalle: lo que
  // se carga aquí ya está en caché al elegir un proyecto.
  const indices = useQueries({
    queries: projects.map((p) => ({
      queryKey: ["continuity", orgId, p],
      queryFn: () => getContinuity(accessToken, orgId, p),
      enabled: Boolean(accessToken && orgId),
    })),
  });

  if (projectsQuery.isPending || indices.some((q) => q.isPending)) {
    return (
      <div className="space-y-2" aria-busy="true">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}
      </div>
    );
  }
  if (projectsQuery.isError || indices.some((q) => q.isError)) {
    return <p role="alert" className="text-sm text-red-700">No se pudo calcular el riesgo por proyecto.</p>;
  }

  const filas = projects
    .map((p, i) => ({ project: p, score: indices[i]?.data?.score ?? null }))
    // Del más expuesto al más cubierto; los que no se pueden medir, al final.
    .sort((a, b) => (a.score ?? Infinity) - (b.score ?? Infinity));
  const visibles = limit ? filas.slice(0, limit) : filas;

  return (
    <ul className="space-y-1.5">
      {visibles.map(({ project, score }) => {
        const band = continuityBand(score);
        const activo = project === activeProject;
        return (
          <li key={project}>
            {hrefFor ? (
              <Link href={hrefFor(project)} className={cn(
                "grid w-full grid-cols-[minmax(0,6.5rem)_1fr_2rem_auto] items-center gap-2 rounded-lg px-2 py-1.5 text-left transition sm:grid-cols-[minmax(0,11rem)_1fr_2.5rem_7rem] sm:gap-3",
                "hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                activo && "bg-primary/5 ring-1 ring-primary/30",
              )}>
              <span data-testid="proyecto" className="truncate text-sm font-medium text-zinc-900">
                {project}
              </span>
              <span className="h-2 rounded-full bg-zinc-100" aria-hidden="true">
                <span
                  className={cn("block h-2 rounded-full", band.bar)}
                  style={{ width: `${score ?? 0}%` }}
                />
              </span>
              <span className={cn("text-right text-sm font-semibold tabular-nums", band.text)}>
                {score ?? "—"}
              </span>
              <span
                className={cn(
                  "inline-flex justify-self-end whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
                  band.chip,
                )}
              >
                {band.label}
              </span>
              </Link>
            ) : (
              <button
                type="button"
                aria-pressed={activo}
                onClick={() => onSelect?.(project)}
                className={cn(
                "grid w-full grid-cols-[minmax(0,6.5rem)_1fr_2rem_auto] items-center gap-2 rounded-lg px-2 py-1.5 text-left transition sm:grid-cols-[minmax(0,11rem)_1fr_2.5rem_7rem] sm:gap-3",
                "hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                activo && "bg-primary/5 ring-1 ring-primary/30",
              )}>
              <span data-testid="proyecto" className="truncate text-sm font-medium text-zinc-900">
                {project}
              </span>
              <span className="h-2 rounded-full bg-zinc-100" aria-hidden="true">
                <span
                  className={cn("block h-2 rounded-full", band.bar)}
                  style={{ width: `${score ?? 0}%` }}
                />
              </span>
              <span className={cn("text-right text-sm font-semibold tabular-nums", band.text)}>
                {score ?? "—"}
              </span>
              <span
                className={cn(
                  "inline-flex justify-self-end whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
                  band.chip,
                )}
              >
                {band.label}
              </span>
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
