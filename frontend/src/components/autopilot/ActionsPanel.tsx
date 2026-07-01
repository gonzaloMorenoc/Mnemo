"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { getActions, proposeActions, approveAction, rejectAction } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";

const KIND_LABEL: Record<string, string> = {
  quarantine: "Cuarentena",
  ticket: "Ticket",
  self_heal: "Auto-reparación",
};

const KIND_EFFECT: Record<string, string> = {
  quarantine: "Esto pondrá el test en cuarentena en el sistema de CI.",
  ticket: "Esto abrirá un ticket en el gestor de incidencias.",
  self_heal: "Esto aplicará una auto-reparación al test afectado.",
};

function getKindEffect(kind: string): string {
  return KIND_EFFECT[kind] ?? "Esto ejecutará la acción sobre el test.";
}

export function ActionsPanel({ runId, orgId }: { runId: string; orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ["actions", orgId, runId];

  const query = useQuery({
    queryKey: key,
    queryFn: async () => (await getActions(accessToken!, orgId)).filter((a) => a.run_id === runId),
    enabled: Boolean(accessToken && orgId && runId),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: key });
  const propose = useMutation({
    mutationFn: () => proposeActions(accessToken!, runId),
    onSuccess: () => { toast.success("Acciones propuestas."); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const approve = useMutation({
    mutationFn: (id: string) => approveAction(accessToken!, id),
    onSuccess: () => { toast.success("Acción aprobada."); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const reject = useMutation({
    mutationFn: (id: string) => rejectAction(accessToken!, id),
    onSuccess: () => { toast.success("Acción rechazada."); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });

  const actions = query.data ?? [];
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-1 text-sm font-medium text-zinc-700">
          Acciones (Nivel 2)
          <InfoTooltip term="triaje" label="Qué es: Acciones de Nivel 2" />
        </h2>
        <Button size="sm" variant="ghost" disabled={propose.isPending} onClick={() => propose.mutate()}>
          {propose.isPending ? "Proponiendo…" : "Proponer acciones"}
        </Button>
      </div>
      {actions.length === 0 ? (
        <p className="text-sm text-zinc-500">Sin acciones para este run.</p>
      ) : (
        <ul className="space-y-2">
          {actions.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex-1">
                <Badge>{KIND_LABEL[a.kind] ?? a.kind}</Badge>{" "}
                <span className="text-zinc-700">{a.summary}</span>
              </span>
              {a.status === "proposed" ? (
                <span className="flex gap-2">
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button size="sm" disabled={approve.isPending}>Aprobar</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogTitle>¿Aprobar acción?</AlertDialogTitle>
                      <AlertDialogDescription>
                        {getKindEffect(a.kind)}
                      </AlertDialogDescription>
                      <div className="mt-4 flex justify-end gap-3">
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction onClick={() => approve.mutate(a.id)}>
                          Confirmar
                        </AlertDialogAction>
                      </div>
                    </AlertDialogContent>
                  </AlertDialog>

                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button size="sm" variant="ghost" disabled={reject.isPending}>Rechazar</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogTitle>¿Rechazar acción?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Esta acción será descartada y no se ejecutará ningún cambio.
                      </AlertDialogDescription>
                      <div className="mt-4 flex justify-end gap-3">
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction onClick={() => reject.mutate(a.id)}>
                          Confirmar
                        </AlertDialogAction>
                      </div>
                    </AlertDialogContent>
                  </AlertDialog>
                </span>
              ) : a.artifact_ref ? (
                <a className="text-blue-600 underline" href={a.artifact_ref} target="_blank" rel="noreferrer">{a.status}</a>
              ) : (
                <Badge>{a.status}</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
