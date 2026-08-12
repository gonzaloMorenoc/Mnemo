"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CloudDownload } from "lucide-react";

import { useAuth } from "@/components/providers/auth-provider";
import { getJiraConfig, importKnowledge } from "@/lib/api/endpoints";
import type { KnowledgeImportResult } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const MAX_REFS = 10;

function parseRefs(raw: string): string[] {
  return raw.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
}

function summary(r: KnowledgeImportResult): string {
  const parts: string[] = [];
  if (r.created.length) parts.push(`${r.created.length} nueva${r.created.length === 1 ? "" : "s"}`);
  if (r.refreshed.length) parts.push(`${r.refreshed.length} refrescada${r.refreshed.length === 1 ? "" : "s"}`);
  if (r.skipped.length) parts.push(`${r.skipped.length} omitida${r.skipped.length === 1 ? "" : "s"} (ya resueltas)`);
  return parts.length ? parts.join(" · ") : "Sin propuestas nuevas";
}

/**
 * Secciones que no entraron, por página. Un tope silencioso se lee como «se importó
 * todo»: si algo se queda fuera, hay que decirlo.
 */
function sectionsNotice(r: KnowledgeImportResult): string | null {
  const total = (r.skipped_sections ?? []).reduce((n, s) => n + s.descartadas, 0);
  if (!total) return null;
  const paginas = (r.skipped_sections ?? []).length;
  return `${total} sección${total === 1 ? "" : "es"} de ${paginas} página${
    paginas === 1 ? "" : "s"
  } no entraron (tope por página o cupo de esta hora). Vuelve a importarlas más tarde.`;
}

export function KnowledgeImportPanel({ orgId }: { orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [raw, setRaw] = useState("");
  const [result, setResult] = useState<KnowledgeImportResult | null>(null);

  const config = useQuery({
    queryKey: ["jira-config", orgId],
    queryFn: () => getJiraConfig(accessToken!, orgId),
    enabled: Boolean(accessToken && orgId),
  });

  const refs = parseRefs(raw);
  const tooMany = refs.length > MAX_REFS;

  const importMut = useMutation({
    mutationFn: () => importKnowledge(accessToken!, orgId, refs),
    onSuccess: (r) => {
      setResult(r);
      setRaw("");
      toast.success(summary(r));
      qc.invalidateQueries({ queryKey: ["knowledge-proposals", orgId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card className="max-w-2xl space-y-4 p-5">
      <h2 className="flex items-center gap-1.5 text-sm font-medium text-zinc-700">
        <CloudDownload size={14} className="text-zinc-400" />
        Importar desde Jira/Confluence
      </h2>
      <p className="text-sm text-zinc-500">
        Convierte issues y páginas en propuestas de lección. Nada entra en la memoria
        sin tu aprobación: todo pasa por la bandeja de propuestas.
      </p>

      {config.data && !config.data.configured ? (
        <p className="rounded-xl border border-dashed border-zinc-200 bg-zinc-50/60 p-4 text-sm text-zinc-600">
          Conecta tu Atlassian primero en{" "}
          <Link href="/app/integrations" className="font-medium text-zinc-900 underline underline-offset-2">
            Integraciones
          </Link>
          .
        </p>
      ) : (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="import-refs">
              Claves de Jira o URLs de páginas de Confluence (una por línea o separadas por comas)
            </Label>
            <Textarea
              id="import-refs"
              rows={3}
              placeholder={"PAY-123\nhttps://tu-site.atlassian.net/wiki/spaces/QA/pages/12345/..."}
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
            />
            <p className={`text-xs ${tooMany ? "font-medium text-red-600" : "text-zinc-400"}`}>
              {refs.length}/{MAX_REFS}
            </p>
          </div>
          <Button
            disabled={importMut.isPending || refs.length === 0 || tooMany}
            onClick={() => importMut.mutate()}
          >
            {importMut.isPending ? "Importando…" : "Generar propuestas"}
          </Button>

          {result && (
            <div className="space-y-1 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-sm">
              <p className="font-medium text-zinc-900">{summary(result)}</p>
              {sectionsNotice(result) && (
                <p className="text-xs text-amber-700">{sectionsNotice(result)}</p>
              )}
              {result.errors.map((e) => (
                <p key={e.ref} className="text-xs text-red-600">
                  {e.ref}: {e.reason}
                </p>
              ))}
              {(result.created.length > 0 || result.refreshed.length > 0) && (
                <Button asChild size="sm" variant="outline" className="mt-1">
                  <Link href="/app/knowledge?tab=propuestas">Ver propuestas</Link>
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
