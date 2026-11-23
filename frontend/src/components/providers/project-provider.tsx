"use client";

import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { listProjects } from "@/lib/api/endpoints";
import type { Project } from "@/lib/api/types";

interface ProjectContextValue {
  /** Proyectos activos (no archivados) de la organización activa. */
  projects: Project[];
  /** Clave del proyecto activo; "" = todos los proyectos. */
  activeProject: string;
  setActiveProject: (key: string) => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);
const STORAGE_PREFIX = "mnemo.activeProject.";

function readStored(orgId: string): string {
  if (typeof window === "undefined" || !orgId) return "";
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + orgId) ?? "";
  } catch {
    return "";
  }
}

/**
 * Proyecto activo, recordado POR ORGANIZACIÓN. Filtra preguntas, búsquedas y
 * onboarding: lo del proyecto + lo de toda la organización. "" = sin filtro.
 */
export function ProjectProvider({ children }: PropsWithChildren) {
  const { accessToken } = useAuth();
  const { activeOrgId } = useActiveOrg();
  // Elección explícita por org en esta sesión (sobrevive a cambiar de org y volver).
  const [explicit, setExplicit] = useState<Record<string, string>>({});

  const query = useQuery({
    queryKey: ["projects", activeOrgId, "active"],
    queryFn: () => listProjects(accessToken!, activeOrgId, false),
    enabled: Boolean(accessToken && activeOrgId),
    staleTime: 60_000,
  });
  const projects = useMemo(() => query.data ?? [], [query.data]);

  const activeProject = useMemo(() => {
    const wanted = explicit[activeOrgId] ?? readStored(activeOrgId);
    // Un proyecto archivado o de otra cuenta deja de filtrar: vuelve a «todos».
    return wanted && projects.some((p) => p.key === wanted) ? wanted : "";
  }, [explicit, activeOrgId, projects]);

  function setActiveProject(key: string) {
    setExplicit((prev) => ({ ...prev, [activeOrgId]: key }));
    try {
      if (key) window.localStorage.setItem(STORAGE_PREFIX + activeOrgId, key);
      else window.localStorage.removeItem(STORAGE_PREFIX + activeOrgId);
    } catch {
      /* almacenamiento bloqueado: la elección dura lo que la sesión */
    }
  }

  return (
    <ProjectContext.Provider value={{ projects, activeProject, setActiveProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

// Fuera del shell (o en tests de una página suelta): sin proyectos ni filtro.
const NO_PROJECT: ProjectContextValue = {
  projects: [],
  activeProject: "",
  setActiveProject: () => {},
};

export function useActiveProject(): ProjectContextValue {
  return useContext(ProjectContext) ?? NO_PROJECT;
}

/** Para el cuerpo de las peticiones: sin clave cuando el filtro es «todos». */
export function projectParam(activeProject: string): { project?: string } {
  return activeProject ? { project: activeProject } : {};
}
