"use client";

import { useState } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { ingestReport } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function RunSelector({ orgId, onRunId }: { orgId: string; onRunId: (id: string) => void }) {
  const { accessToken } = useAuth();
  const [project, setProject] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [manualId, setManualId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
          <Input id="file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting}>{submitting ? "Procesando…" : "Analizar run"}</Button>
      </form>
      <div className="flex items-end gap-2 border-t border-zinc-100 pt-4">
        <div className="flex-1 space-y-1">
          <Label htmlFor="manual">…o abre un run existente</Label>
          <Input id="manual" value={manualId} onChange={(e) => setManualId(e.target.value)} placeholder="identificador (UUID) del run" />
        </div>
        <Button variant="ghost" type="button" disabled={!manualId} onClick={() => onRunId(manualId.trim())}>Cargar</Button>
      </div>
    </Card>
  );
}
