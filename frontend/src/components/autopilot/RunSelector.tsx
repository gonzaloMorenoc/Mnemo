"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { ingestReport, listRuns } from "@/lib/api/endpoints";
import { VerdictBadge } from "@/components/ui/verdict-badge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileDropzone } from "@/components/ui/file-dropzone";

export function RunSelector({ orgId, onRunId }: { orgId: string; onRunId: (id: string) => void }) {
  const { accessToken } = useAuth();
  const [project, setProject] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [manualId, setManualId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const runsQuery = useQuery({
    queryKey: ["runs", orgId],
    queryFn: () => listRuns(accessToken!, orgId, { limit: 8 }),
    enabled: Boolean(accessToken && orgId),
  });
  const runs = runsQuery.data ?? [];

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file || !orgId) {
      setError("Falta archivo u organización.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("project", project || "default");
    form.append("source", "auto");
    form.append("org_id", orgId);
    setSubmitting(true);
    try {
      const res = await ingestReport(accessToken!, form);
      onRunId(res.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al ingerir el reporte.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="max-w-xl space-y-4 p-5">
      <form onSubmit={handleUpload} className="space-y-4">
        <div className="space-y-1">
          <Label htmlFor="project">Proyecto</Label>
          <Input id="project" value={project} onChange={(e) => setProject(e.target.value)} placeholder="cliente-a" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="file">Reporte de test</Label>
          <FileDropzone
            id="file"
            file={file}
            onFile={setFile}
            hint="JUnit, TestNG, Robot, Allure, Playwright, Cypress o Cucumber — se autodetecta"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting}>{submitting ? "Procesando…" : "Analizar run"}</Button>
      </form>
      {/* Histórico navegable: adiós al "pega un UUID" como única vía */}
      <div className="space-y-2 border-t border-zinc-100 pt-4">
        <p className="text-xs font-medium text-zinc-500">Runs recientes</p>
        {runsQuery.isLoading && <p className="text-sm text-zinc-400">Cargando…</p>}
        {!runsQuery.isLoading && runs.length === 0 && (
          <p className="text-sm text-zinc-500">Aún no hay runs. Sube un reporte para empezar.</p>
        )}
        <ul className="space-y-1.5">
          {runs.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onRunId(r.id)}
                className="flex w-full items-center justify-between gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm hover:bg-zinc-50"
              >
                <span className="min-w-0">
                  <span className="font-medium text-zinc-900">{r.project}</span>
                  <span className="ml-2 text-xs text-zinc-400">
                    {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {r.failures > 0 && (
                    <span className="text-xs text-zinc-500">{r.failures} fallos</span>
                  )}
                  <VerdictBadge verdict={r.verdict} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex items-end gap-2 border-t border-zinc-100 pt-4">
        <div className="flex-1 space-y-1">
          <Label htmlFor="manual">…o abre un run por identificador</Label>
          <Input id="manual" value={manualId} onChange={(e) => setManualId(e.target.value)} placeholder="identificador (UUID) del run" />
        </div>
        <Button variant="ghost" type="button" disabled={!manualId} onClick={() => onRunId(manualId.trim())}>Cargar</Button>
      </div>
    </Card>
  );
}
