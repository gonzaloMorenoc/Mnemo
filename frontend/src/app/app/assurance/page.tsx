"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { getAssuranceVerdict, ingestReport } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { FileDropzone } from "@/components/ui/file-dropzone";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function AssurancePage() {
  const { accessToken } = useAuth();
  const { activeOrgId: orgId } = useActiveOrg();
  const [project, setProject] = useState("");
  const [source, setSource] = useState("auto");
  const [file, setFile] = useState<File | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const verdictQuery = useQuery({
    queryKey: ["verdict", runId],
    queryFn: () => getAssuranceVerdict(accessToken!, runId!),
    enabled: Boolean(accessToken && runId),
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setRunId(null); // descarta el veredicto del run anterior antes de ingerir el nuevo
    if (!file || !orgId) {
      setError("Falta archivo u organización.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("project", project || "default");
    form.append("source", source);
    form.append("org_id", orgId);
    setSubmitting(true);
    try {
      const res = await ingestReport(accessToken!, form);
      setRunId(res.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al ingerir el reporte.");
    } finally {
      setSubmitting(false);
    }
  }

  const v = verdictQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Assurance</h1>
        <p className="text-sm text-zinc-500">
          Veredicto exprés contra la memoria: cuántos fallos ya conocemos y cuántos son
          nuevos. Para el análisis completo con acta, usa Autopilot.
        </p>
      </div>

      <Card className="max-w-xl space-y-4 p-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="project">Proyecto</Label>
            <Input id="project" value={project} onChange={(e) => setProject(e.target.value)} placeholder="cliente-a" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="source">Formato</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger id="source" aria-label="Formato">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto-detectar</SelectItem>
                <SelectItem value="allure">Allure (JSON)</SelectItem>
                <SelectItem value="junit">JUnit (XML)</SelectItem>
                <SelectItem value="testng">TestNG (XML)</SelectItem>
                <SelectItem value="cucumber">Cucumber (JSON)</SelectItem>
                <SelectItem value="playwright">Playwright (JSON)</SelectItem>
                <SelectItem value="cypress">Cypress / Mochawesome (JSON)</SelectItem>
                <SelectItem value="robot">Robot Framework (XML)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="file">Reporte</Label>
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
      </Card>

      {runId && verdictQuery.isError && (
        <Card className="max-w-xl p-5">
          <p className="text-sm text-red-600">No se pudo cargar el veredicto del run.</p>
        </Card>
      )}

      {v && (
        <Card className="max-w-xl space-y-3 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-700">Veredicto del run</h2>
            <Badge>{v.risk === "atencion" ? "Atención" : "OK"}</Badge>
          </div>
          <div className="flex gap-4 text-sm text-zinc-600">
            <span><strong className="text-zinc-900">{v.known}</strong> conocidos</span>
            <span><strong className="text-zinc-900">{v.novel}</strong> nuevos</span>
            <span><strong className="text-zinc-900">{v.ingested}</strong> totales</span>
          </div>
          <div className="text-xs text-zinc-400">
            Conocidos = ya estaban en una familia de defectos; nuevos = primera vez que los vemos.
          </div>
          {v.top_families.length > 0 && (
            <ul className="space-y-1 text-sm text-zinc-600">
              {v.top_families.map((f) => (
                <li key={f.id} className="flex items-center justify-between">
                  <span>{f.title}</span>
                  <span className="flex items-center gap-2">
                    <Badge title={`${f.occurrence_count} ocurrencias en total`}>{f.occurrence_count}x</Badge>
                    {f.recurring && <Badge title="Visto en varios runs">recurrente</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {v.narrative && <p className="text-sm text-zinc-700">{v.narrative}</p>}
        </Card>
      )}
    </div>
  );
}
