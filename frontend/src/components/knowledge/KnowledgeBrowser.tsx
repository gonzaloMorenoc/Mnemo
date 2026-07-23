"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { deleteKnowledge, listKnowledge, updateKnowledge } from "@/lib/api/endpoints";
import type { KnowledgeItem } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const KIND_LABEL: Record<string, string> = {
  regla_negocio: "Regla de negocio",
  flujo: "Flujo",
  riesgo: "Riesgo",
  glosario: "Glosario",
  leccion: "Lección",
  reto: "Reto",
  patron: "Patrón",
};

export function KnowledgeBrowser({ orgId }: { orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [kind, setKind] = useState("todos");
  const [status, setStatus] = useState("todos");
  const [project, setProject] = useState("todos");

  const query = useQuery({
    queryKey: ["knowledge-browse", orgId, kind, status],
    queryFn: () =>
      listKnowledge(accessToken!, orgId, {
        ...(kind !== "todos" ? { kind } : {}),
        ...(status !== "todos" ? { status } : {}),
      }),
    enabled: Boolean(accessToken && orgId),
  });
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["knowledge-browse", orgId] });

  const items = query.data ?? [];
  // Proyectos presentes en los datos cargados → opciones del filtro (client-side)
  const projects = Array.from(
    new Set(items.map((i) => i.project).filter((p): p is string => Boolean(p))),
  ).sort();
  const visible = project === "todos" ? items : items.filter((i) => i.project === project);

  return (
    <Card className="max-w-2xl">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-base">
          Explorar la memoria
          {visible.length > 0 && <Badge>{visible.length}</Badge>}
        </CardTitle>
        <div className="flex flex-wrap justify-end gap-2">
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="w-[160px]" aria-label="Filtrar por tipo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todos los tipos</SelectItem>
              {Object.entries(KIND_LABEL).map(([v, l]) => (
                <SelectItem key={v} value={v}>{l}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-[130px]" aria-label="Filtrar por estado">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todos">Todo estado</SelectItem>
              <SelectItem value="activo">Activo</SelectItem>
              <SelectItem value="obsoleto">Obsoleto</SelectItem>
            </SelectContent>
          </Select>
          {projects.length > 0 && (
            <Select value={project} onValueChange={setProject}>
              <SelectTrigger className="w-[170px]" aria-label="Filtrar por proyecto">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todos">Todos los proyectos</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isLoading ? (
          <p className="text-sm text-zinc-500">Cargando…</p>
        ) : visible.length === 0 ? (
          <p className="text-sm text-zinc-500">Sin resultados con estos filtros.</p>
        ) : (
          visible.map((it) => (
            <ItemCard key={it.id} item={it} orgId={orgId} token={accessToken!} onDone={invalidate} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ItemCard({
  item,
  orgId,
  token,
  onDone,
}: {
  item: KnowledgeItem;
  orgId: string;
  token: string;
  onDone: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    title: item.title ?? "",
    challenge: item.challenge ?? "",
    approach: item.approach ?? "",
    outcome: item.outcome ?? "",
    domain: item.domain ?? "",
    tags: (item.tags ?? []).join(", "),
  });
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      updateKnowledge(token, item.id, { org_id: orgId, ...body }),
    onSuccess: () => {
      toast.success("Guardado.");
      setEditing(false);
      onDone();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const del = useMutation({
    mutationFn: () => deleteKnowledge(token, item.id, orgId),
    onSuccess: () => {
      toast.success("Borrado.");
      onDone();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const obsoleto = item.status === "obsoleto";
  const busy = update.isPending || del.isPending;

  return (
    <div className={`space-y-2 rounded-xl border border-zinc-200 p-3 ${obsoleto ? "bg-zinc-50 opacity-70" : "bg-white"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{KIND_LABEL[item.kind] ?? item.kind}</Badge>
        {item.project && (
          <Badge className="border-blue-200 bg-blue-50 text-blue-700">{item.project}</Badge>
        )}
        {item.domain && <Badge variant="user">{item.domain}</Badge>}
        {obsoleto && <Badge className="bg-amber-100 text-amber-800">Obsoleto</Badge>}
        {item.source === "auto_triage" && (
          <span className="text-xs text-zinc-500">inferida del triaje</span>
        )}
        {item.source_url && (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-zinc-500 underline underline-offset-2 hover:text-zinc-900"
          >
            Ver original ↗
          </a>
        )}
      </div>
      <p className="text-sm font-medium text-zinc-900">{item.title}</p>
      {!editing && item.challenge && (
        <p className="text-sm text-zinc-600 line-clamp-2">{item.challenge}</p>
      )}

      {editing && (
        <div className="space-y-2">
          <div className="space-y-1.5">
            <Label htmlFor={`bt-${item.id}`}>Título</Label>
            <Input id={`bt-${item.id}`} maxLength={300} value={form.title} onChange={(e) => set("title", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`bc-${item.id}`}>Reto / problema</Label>
            <Textarea id={`bc-${item.id}`} rows={3} maxLength={4000} value={form.challenge} onChange={(e) => set("challenge", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`ba-${item.id}`}>Enfoque / solución</Label>
            <Textarea id={`ba-${item.id}`} rows={3} maxLength={4000} value={form.approach} onChange={(e) => set("approach", e.target.value)} />
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`bd-${item.id}`}>Dominio</Label>
              <Input id={`bd-${item.id}`} maxLength={300} value={form.domain} onChange={(e) => set("domain", e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`bg-${item.id}`}>Etiquetas (coma)</Label>
              <Input id={`bg-${item.id}`} value={form.tags} onChange={(e) => set("tags", e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`bo-${item.id}`}>Resultado</Label>
            <Textarea id={`bo-${item.id}`} rows={2} maxLength={4000} value={form.outcome} onChange={(e) => set("outcome", e.target.value)} />
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2">
        {editing ? (
          <>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
              Cancelar
            </Button>
            <Button
              size="sm"
              disabled={busy || !form.title.trim()}
              onClick={() =>
                update.mutate({
                  title: form.title,
                  challenge: form.challenge || null,
                  approach: form.approach || null,
                  outcome: form.outcome || null,
                  domain: form.domain || null,
                  tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
                })
              }
            >
              {update.isPending ? "Guardando…" : "Guardar"}
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(true)}>
              Editar
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => update.mutate({ status: obsoleto ? "activo" : "obsoleto" })}
            >
              {obsoleto ? "Reactivar" : "Marcar obsoleto"}
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button size="sm" variant="ghost" disabled={busy}>Borrar</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogTitle>¿Borrar este conocimiento?</AlertDialogTitle>
                <AlertDialogDescription>
                  Borrado definitivo (para errores). Si el conocimiento quedó desfasado,
                  usa &quot;Marcar obsoleto&quot; — se conserva pero deja de usarse en las respuestas.
                </AlertDialogDescription>
                <div className="mt-4 flex justify-end gap-3">
                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                  <AlertDialogAction onClick={() => del.mutate()}>Borrar</AlertDialogAction>
                </div>
              </AlertDialogContent>
            </AlertDialog>
          </>
        )}
      </div>
    </div>
  );
}
