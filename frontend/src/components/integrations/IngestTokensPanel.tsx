"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, KeyRound } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import {
  createIngestToken,
  listIngestTokens,
  revokeIngestToken,
} from "@/lib/api/endpoints";
import type { IngestTokenCreated } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const BACKEND = process.env.NEXT_PUBLIC_API_BASE_URL || "https://<backend>";

function curlFor(token: string): string {
  return [
    `curl -H "Authorization: Bearer ${token}" \\`,
    `     -F file=@test-results/junit.xml \\`,
    `     -F project=mi-proyecto \\`,
    `     ${BACKEND}/v2/ci/ingest`,
  ].join("\n");
}

export function IngestTokensPanel({ orgId }: { orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  // El claro solo existe en la respuesta de creación → se enseña UNA vez aquí.
  const [created, setCreated] = useState<IngestTokenCreated | null>(null);

  const tokensQuery = useQuery({
    queryKey: ["ingest-tokens", orgId],
    queryFn: () => listIngestTokens(accessToken!, orgId),
    enabled: Boolean(accessToken && orgId),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["ingest-tokens", orgId] });

  const create = useMutation({
    mutationFn: () => createIngestToken(accessToken!, orgId, name.trim()),
    onSuccess: (t) => {
      setCreated(t);
      setName("");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => revokeIngestToken(accessToken!, id),
    onSuccess: () => {
      toast.success("Token revocado.");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  async function copy(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copiado.`);
    } catch {
      toast.error("No se pudo copiar — selecciona y copia a mano.");
    }
  }

  const tokens = tokensQuery.data ?? [];

  return (
    <Card className="max-w-xl space-y-4 p-5">
      <h2 className="flex items-center gap-1.5 text-sm font-medium text-zinc-700">
        <KeyRound size={14} className="text-zinc-400" />
        Tokens de ingesta CI
      </h2>
      <p className="text-sm text-zinc-500">
        Conecta cualquier CI (JUnit, TestNG, Robot, Allure, Playwright, Cypress o Cucumber)
        sin instalar nada: sube el reporte con un token y Mnemo hace el resto — triaje,
        acta firmada y gate.
      </p>

      {/* Crear */}
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="flex-1 space-y-1">
          <Label htmlFor="token-name">Nombre del token</Label>
          <Input
            id="token-name"
            placeholder="p.ej. GitHub Actions · proyecto web"
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={create.isPending || !name.trim()}>
          {create.isPending ? "Creando…" : "Crear token"}
        </Button>
      </form>

      {/* Token recién creado: única vez que se muestra el claro */}
      {created && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-900">
            Copia el token ahora — no volverá a mostrarse.
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 font-mono text-xs text-zinc-800">
              {created.token}
            </code>
            <Button size="sm" variant="outline" onClick={() => copy(created.token, "Token")}>
              <Copy size={13} />
            </Button>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-amber-900">Desde tu CI (un paso de shell):</p>
            <div className="flex items-start gap-2">
              <pre className="min-w-0 flex-1 overflow-x-auto rounded bg-zinc-900 p-2 text-[11px] leading-relaxed text-zinc-100">
                {curlFor(created.token)}
              </pre>
              <Button size="sm" variant="outline" onClick={() => copy(curlFor(created.token), "Comando")}>
                <Copy size={13} />
              </Button>
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setCreated(null)}>
            Hecho, lo he guardado
          </Button>
        </div>
      )}

      {/* Lista */}
      {tokens.length > 0 && (
        <ul className="divide-y divide-zinc-100">
          {tokens.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="min-w-0">
                <span className="font-medium text-zinc-900">{t.name}</span>
                <span className="ml-2 text-xs text-zinc-400">
                  {t.created_at ? `creado ${t.created_at.slice(0, 10)}` : ""}
                  {t.last_used_at ? ` · último uso ${t.last_used_at.slice(0, 10)}` : " · sin usar"}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {t.revoked_at ? (
                  <Badge className="border-zinc-200 bg-zinc-50 text-zinc-500">Revocado</Badge>
                ) : (
                  <>
                    <Badge className="border-emerald-200 bg-emerald-100 text-emerald-800">Activo</Badge>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button size="sm" variant="ghost" disabled={revoke.isPending}>
                          Revocar
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogTitle>¿Revocar este token?</AlertDialogTitle>
                        <AlertDialogDescription>
                          Los CIs que lo usen dejarán de poder ingerir reportes inmediatamente.
                          Esta acción no se puede deshacer.
                        </AlertDialogDescription>
                        <div className="mt-4 flex justify-end gap-3">
                          <AlertDialogCancel>Cancelar</AlertDialogCancel>
                          <AlertDialogAction onClick={() => revoke.mutate(t.id)}>
                            Revocar
                          </AlertDialogAction>
                        </div>
                      </AlertDialogContent>
                    </AlertDialog>
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
