"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { getPublicEnv } from "@/lib/env";
import {
  createIngestToken,
  listIngestTokens,
  listProjects,
  revokeIngestToken,
} from "@/lib/api/endpoints";
import type { IngestTokenCreated } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const ALL_ORG = "";
const EXPIRY_OPTIONS = [
  { days: 30, label: "30 días" },
  { days: 90, label: "90 días" },
  { days: 365, label: "1 año" },
  { days: 0, label: "Sin caducidad" },
];

/** Configuración de cada cliente. NUNCA incrusta el secreto: variable de entorno o
 *  campo de contraseña del propio cliente, para que no acabe en un repositorio. */
export function clientSnippets(mcpUrl: string): { id: string; label: string; text: string }[] {
  return [
    {
      id: "claude",
      label: "Claude Code",
      text: [
        `claude mcp add --transport http mnemo ${mcpUrl} \\`,
        `  --header "Authorization: Bearer $MNEMO_READ_TOKEN"`,
      ].join("\n"),
    },
    {
      id: "cursor",
      label: "Cursor",
      text: JSON.stringify({
        mcpServers: {
          mnemo: { url: mcpUrl, headers: { Authorization: "Bearer ${env:MNEMO_READ_TOKEN}" } },
        },
      }, null, 2),
    },
    {
      id: "vscode",
      label: "VS Code (Copilot)",
      text: JSON.stringify({
        servers: {
          mnemo: {
            type: "http",
            url: mcpUrl,
            headers: { Authorization: "Bearer ${input:mnemo-token}" },
          },
        },
        inputs: [{ type: "promptString", id: "mnemo-token",
                   description: "Token de lectura de Mnemo", password: true }],
      }, null, 2),
    },
  ];
}

/**
 * Tokens de SOLO LECTURA para que el asistente de IA del consultor (Claude Code,
 * Cursor, Copilot) consulte la memoria del equipo por MCP. No pueden escribir ni
 * ingerir; atados a un proyecto, no ven otros.
 */
export function ReadTokensPanel({ orgId }: { orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [project, setProject] = useState(ALL_ORG);
  const [expiry, setExpiry] = useState(90);
  const [client, setClient] = useState("claude");
  const [created, setCreated] = useState<{ data: IngestTokenCreated; orgId: string } | null>(
    null,
  );
  // Solo si el backend lo creó DE LECTURA: uno anterior a la 037 ignora `scope` y
  // devolvería un token de ingesta, que no debe presentarse como de MCP.
  const createdForThisOrg =
    created && created.orgId === orgId && created.data.token.startsWith("mnemo_rt_")
      ? created.data : null;
  const mcpUrl = `${getPublicEnv().apiBaseUrl}/mcp`;
  const snippets = clientSnippets(mcpUrl);
  const snippet = snippets.find((s) => s.id === client) ?? snippets[0];

  const enabled = Boolean(accessToken && orgId);
  const tokensQuery = useQuery({
    queryKey: ["read-tokens", orgId],
    queryFn: () => listIngestTokens(accessToken!, orgId, "read"),
    enabled,
  });
  const projectsQuery = useQuery({
    queryKey: ["projects", orgId, "active"],
    queryFn: () => listProjects(accessToken!, orgId, false),
    enabled,
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["read-tokens", orgId] });

  const create = useMutation({
    mutationFn: () =>
      createIngestToken(accessToken!, orgId, name.trim(), {
        scope: "read",
        ...(project ? { project } : {}),
        ...(expiry ? { expires_in_days: expiry } : {}),
      }),
    onSuccess: (t) => {
      if (!t.token.startsWith("mnemo_rt_")) {
        toast.error("El servidor aún no admite tokens de lectura. Revoca el creado y "
                    + "vuelve a intentarlo en unos minutos.");
      }
      setCreated({ data: t, orgId });
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
  const projects = projectsQuery.data ?? [];

  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-500">
        Conecta tu asistente de IA (Claude Code, Cursor, Copilot) a la memoria del equipo:
        cuando un test falla, puede preguntar a Mnemo qué se sabe de él — la etiqueta, la razón
        que dio una persona y las lecciones. Solo lectura: el token no puede escribir nada.
      </p>

      <form
        className="grid gap-2 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="space-y-1">
          <Label htmlFor="read-token-name">Nombre</Label>
          <Input id="read-token-name" placeholder="p.ej. Claude Code · Ana" maxLength={100}
                 value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="read-token-project">Alcance</Label>
          <select id="read-token-project" value={project}
                  onChange={(e) => setProject(e.target.value)}
                  className="h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm">
            <option value={ALL_ORG}>Toda la organización</option>
            {projects.map((p) => <option key={p.id} value={p.key}>{p.name}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="read-token-expiry">Caduca</Label>
          <select id="read-token-expiry" value={expiry}
                  onChange={(e) => setExpiry(Number(e.target.value))}
                  className="h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm">
            {EXPIRY_OPTIONS.map((o) => <option key={o.days} value={o.days}>{o.label}</option>)}
          </select>
        </div>
        <Button type="submit" disabled={create.isPending || !name.trim() || !enabled}>
          {create.isPending ? "Creando…" : "Crear token"}
        </Button>
      </form>

      {createdForThisOrg && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="text-sm font-medium text-amber-900">
            Copia el token ahora — no volverá a mostrarse.
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 font-mono text-xs text-zinc-800">
              {createdForThisOrg.token}
            </code>
            <Button size="sm" variant="outline" aria-label="Copiar token"
                    onClick={() => copy(createdForThisOrg.token, "Token")}>
              <Copy size={13} />
            </Button>
          </div>
          <p className="text-xs font-medium text-amber-900">
            Guárdalo como variable de entorno <code>MNEMO_READ_TOKEN</code> y configura tu cliente:
          </p>
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Cliente">
            {snippets.map((s) => (
              <Button key={s.id} type="button" size="sm" role="tab"
                      aria-selected={s.id === client}
                      variant={s.id === client ? "default" : "outline"}
                      onClick={() => setClient(s.id)}>
                {s.label}
              </Button>
            ))}
          </div>
          <div className="flex items-start gap-2">
            <pre className="min-w-0 flex-1 overflow-x-auto rounded bg-zinc-900 p-2 text-[11px] leading-relaxed text-zinc-100">
              {snippet.text}
            </pre>
            <Button size="sm" variant="outline" aria-label="Copiar configuración"
                    onClick={() => copy(snippet.text, "Configuración")}>
              <Copy size={13} />
            </Button>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setCreated(null)}>
            Hecho, lo he guardado
          </Button>
        </div>
      )}

      {tokensQuery.isError && (
        <p className="text-sm text-red-600">No se pudieron cargar los tokens de lectura.</p>
      )}
      {tokens.length > 0 && (
        <ul className="divide-y divide-zinc-100">
          {tokens.map((t) => {
            const expired = Boolean(t.expires_at && new Date(t.expires_at) < new Date());
            return (
              <li key={t.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="min-w-0">
                  <span className="font-medium text-zinc-900">{t.name}</span>
                  <span className="ml-2 text-xs text-zinc-500">
                    {t.project ? `proyecto ${t.project}` : "toda la organización"}
                    {t.expires_at ? ` · caduca ${t.expires_at.slice(0, 10)}` : " · sin caducidad"}
                    {t.last_used_at ? ` · último uso ${t.last_used_at.slice(0, 10)}` : " · sin usar"}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {t.revoked_at ? (
                    <Badge className="border-zinc-200 bg-zinc-50 text-zinc-500">Revocado</Badge>
                  ) : expired ? (
                    <Badge className="border-zinc-200 bg-zinc-50 text-zinc-500">Caducado</Badge>
                  ) : (
                    <Button size="sm" variant="ghost" disabled={revoke.isPending}
                            onClick={() => revoke.mutate(t.id)}>
                      Revocar
                    </Button>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
