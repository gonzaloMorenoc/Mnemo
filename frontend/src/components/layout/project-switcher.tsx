"use client";
import { FolderKanban } from "lucide-react";

import { useActiveProject } from "@/components/providers/project-provider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Radix Select no admite "" como valor de un item: «todos» lleva un centinela.
const ALL = "__all__";

/** Filtro global por proyecto (preguntas, búsqueda, onboarding). Sin proyectos, no se muestra. */
export function ProjectSwitcher() {
  const { projects, activeProject, setActiveProject } = useActiveProject();
  if (projects.length === 0) return null;
  return (
    <Select
      value={activeProject || ALL}
      onValueChange={(v) => setActiveProject(v === ALL ? "" : v)}
    >
      <SelectTrigger
        aria-label="Proyecto"
        className="h-8 max-w-[30vw] rounded-lg px-2 text-sm [&>span]:truncate"
      >
        <FolderKanban size={14} className="mr-1 shrink-0 text-zinc-500" aria-hidden />
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>Todos los proyectos</SelectItem>
        {projects.map((p) => (
          <SelectItem key={p.id} value={p.key}>{p.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
