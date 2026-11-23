"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { isOrgAdmin } from "@/components/org/OrgMembersPanel";
import { useAuth } from "@/components/providers/auth-provider";
import { createProject, listProjects, updateProject } from "@/lib/api/endpoints";
import type { Project } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * Proyectos de la organización. La CLAVE (la que manda el CI) no se cambia nunca: va
 * dentro de las actas firmadas. Un admin edita el nombre visible y archiva; los
 * proyectos nuevos los crea la propia ingesta, o el admin a mano.
 */
export function ProjectsPanel({ org }: { org: { id: string; role?: string | null } }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const admin = isOrgAdmin(org.role);
  const query = useQuery({
    queryKey: ["projects", org.id, "all"],
    queryFn: () => listProjects(accessToken!, org.id, true),
    enabled: Boolean(accessToken && org.id),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["projects", org.id] });

  const projects = query.data ?? [];
  return (
    <div className="space-y-2 border-t border-zinc-200 pt-3">
      <p className="text-xs font-medium text-zinc-500">Proyectos</p>
      {query.isLoading ? null : query.isError ? (
        <p className="text-sm text-red-600">No se pudieron cargar los proyectos.</p>
      ) : projects.length === 0 ? (
        <p className="text-sm text-zinc-500">
          Aún no hay proyectos. Se crean solos con la primera ingesta (el campo `project` del CI).
        </p>
      ) : (
        <ul className="space-y-1.5">
          {projects.map((p) => (
            <ProjectRow key={p.id} project={p} admin={admin} onChanged={refresh} />
          ))}
        </ul>
      )}
      {admin && <NewProjectForm orgId={org.id} onCreated={refresh} />}
    </div>
  );
}

function ProjectRow({ project, admin, onChanged }: {
  project: Project; admin: boolean; onChanged: () => void;
}) {
  const { accessToken } = useAuth();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(project.name);
  const mutation = useMutation({
    mutationFn: (body: { name?: string; archived?: boolean }) =>
      updateProject(accessToken!, project.id, body),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white px-2 py-1.5">
      <div className="min-w-0">
        {editing ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) mutation.mutate({ name: name.trim() });
            }}
          >
            <Input aria-label={`Nombre de ${project.key}`} value={name} maxLength={200}
                   onChange={(e) => setName(e.target.value)} className="h-7 w-48" />
            <Button type="submit" size="sm" disabled={mutation.isPending || !name.trim()}>Guardar</Button>
            <Button type="button" size="sm" variant="ghost"
                    onClick={() => { setEditing(false); setName(project.name); }}>Cancelar</Button>
          </form>
        ) : (
          <span className="font-medium text-zinc-800">{project.name}</span>
        )}
        <span className="block text-xs text-zinc-500">
          clave <code>{project.key}</code> · {project.runs} run{project.runs === 1 ? "" : "s"} ·{" "}
          {project.knowledge} elemento{project.knowledge === 1 ? "" : "s"} de conocimiento
        </span>
      </div>
      <div className="flex items-center gap-2">
        {project.archived && <Badge className="bg-zinc-200 text-zinc-700">archivado</Badge>}
        {admin && !editing && (
          <>
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Renombrar</Button>
            <Button size="sm" variant="ghost" disabled={mutation.isPending}
                    onClick={() => mutation.mutate({ archived: !project.archived })}>
              {project.archived ? "Reactivar" : "Archivar"}
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function NewProjectForm({ orgId, onCreated }: { orgId: string; onCreated: () => void }) {
  const { accessToken } = useAuth();
  const [key, setKey] = useState("");
  const mutation = useMutation({
    mutationFn: () => createProject(accessToken!, { org_id: orgId, key: key.trim() }),
    onSuccess: () => {
      setKey("");
      toast.success("Proyecto creado.");
      onCreated();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <form
      className="flex flex-wrap items-center gap-2 pt-1"
      onSubmit={(e) => {
        e.preventDefault();
        if (key.trim()) mutation.mutate();
      }}
    >
      <Input aria-label="Clave del nuevo proyecto" placeholder="clave-del-proyecto (la del CI)"
             value={key} maxLength={200} onChange={(e) => setKey(e.target.value)}
             className="h-8 w-64" />
      <Button type="submit" size="sm" disabled={mutation.isPending || !key.trim()}>
        Crear proyecto
      </Button>
    </form>
  );
}
