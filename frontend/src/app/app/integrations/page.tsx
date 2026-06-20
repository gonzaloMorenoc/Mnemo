"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import {
  getOrganizations,
  getJiraConfig,
  saveJiraConfig,
  pullJiraBugs,
  ingestJiraFile,
} from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { JiraIngestResponse } from "@/lib/api/types";

export default function IntegrationsPage() {
  const { accessToken } = useAuth();

  // Config form state
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [jql, setJql] = useState("issuetype = Bug");

  // Pull / file state
  const [project, setProject] = useState("");
  const [file, setFile] = useState<File | null>(null);

  // Feedback state
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ── orgs query ──────────────────────────────────────────────────────────
  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgId = orgsQuery.data?.[0]?.id ?? "";

  // ── jira config query ────────────────────────────────────────────────────
  const configQuery = useQuery({
    queryKey: ["jira-config", orgId],
    queryFn: () => getJiraConfig(accessToken!, orgId),
    enabled: Boolean(accessToken && orgId),
  });
  const configured = configQuery.data?.configured ?? false;

  // ── helpers ──────────────────────────────────────────────────────────────
  function clearFeedback() {
    setMsg(null);
    setError(null);
  }

  function showCounts(res: JiraIngestResponse) {
    setMsg(
      `Listo. Ingeridos: ${res.ingested} · Nuevos: ${res.novel} · Conocidos: ${res.known} · Omitidos: ${res.skipped}`,
    );
  }

  // ── save config ──────────────────────────────────────────────────────────
  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    clearFeedback();
    if (!orgId) {
      setError("No se encontró organización.");
      return;
    }
    if (!baseUrl || !email || !token) {
      setError("Base URL, email y API token son obligatorios.");
      return;
    }
    setBusy(true);
    try {
      await saveJiraConfig(accessToken!, {
        org_id: orgId,
        base_url: baseUrl,
        email,
        token,
        jql,
      });
      setToken("");
      await configQuery.refetch();
      setMsg("Configuración de Jira guardada.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar la configuración.");
    } finally {
      setBusy(false);
    }
  }

  // ── pull from API ─────────────────────────────────────────────────────────
  async function handlePull() {
    clearFeedback();
    if (!orgId) {
      setError("No se encontró organización.");
      return;
    }
    setBusy(true);
    try {
      const res = await pullJiraBugs(accessToken!, {
        org_id: orgId,
        project: project || "jira",
      });
      showCounts(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al importar bugs desde Jira.");
    } finally {
      setBusy(false);
    }
  }

  // ── file upload ───────────────────────────────────────────────────────────
  async function handleUpload() {
    clearFeedback();
    if (!file) {
      setError("Selecciona un archivo de exportación.");
      return;
    }
    if (!orgId) {
      setError("No se encontró organización.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("project", project || "jira");
    form.append("org_id", orgId);
    setBusy(true);
    try {
      const res = await ingestJiraFile(accessToken!, form);
      showCounts(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir el export de Jira.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Integraciones</h1>
        <p className="text-sm text-zinc-500">Conecta Jira para importar bugs como defectos rastreables.</p>
      </div>

      {/* ── Config card ─────────────────────────────────────────────────── */}
      <Card className="max-w-xl space-y-4 p-5">
        <h2 className="text-sm font-medium text-zinc-700">Configuración de Jira</h2>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="base-url">Base URL</Label>
            <Input
              id="base-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://tu-empresa.atlassian.net"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="usuario@empresa.com"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="api-token">API Token</Label>
            <Input
              id="api-token"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="jql">JQL por defecto</Label>
            <Input
              id="jql"
              value={jql}
              onChange={(e) => setJql(e.target.value)}
              placeholder="issuetype = Bug"
            />
          </div>
          {configured && (
            <p className="text-xs text-zinc-500">Integración ya configurada. Rellena el token solo para actualizarla.</p>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? "Guardando…" : "Guardar configuración"}
          </Button>
        </form>
      </Card>

      {/* ── Import card ─────────────────────────────────────────────────── */}
      <Card className="max-w-xl space-y-4 p-5">
        <h2 className="text-sm font-medium text-zinc-700">Importar bugs</h2>

        <div className="space-y-1">
          <Label htmlFor="project">Proyecto (slug)</Label>
          <Input
            id="project"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            placeholder="jira"
          />
        </div>

        <div className="space-y-2">
          <Button onClick={handlePull} disabled={busy || !configured}>
            {busy ? "Importando…" : "Importar bugs ahora (API)"}
          </Button>
          {!configured && (
            <p className="text-xs text-zinc-500">Guarda la configuración antes de importar.</p>
          )}
        </div>

        <div className="space-y-2 border-t pt-4">
          <Label htmlFor="export-file">Subir export de Jira (CSV / JSON)</Label>
          <Input
            id="export-file"
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button onClick={handleUpload} disabled={busy || !file}>
            {busy ? "Subiendo…" : "Subir export"}
          </Button>
        </div>

        {msg && <p className="text-sm text-green-600">{msg}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </Card>
    </div>
  );
}
