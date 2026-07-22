"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import {
  getOrganizations,
  getJiraConfig,
  saveJiraConfig,
  pullJiraBugs,
  ingestJiraFile,
  getGithubConfig,
  saveGithubConfig,
  indexRepo,
  listRepoTests,
} from "@/lib/api/endpoints";
import { ApiClientError } from "@/lib/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { FileDropzone } from "@/components/ui/file-dropzone";
import type { JiraIngestResponse } from "@/lib/api/types";

// Página de instalación de la GitHub App (opcional; sin ella se muestran instrucciones).
const GITHUB_APP_URL = process.env.NEXT_PUBLIC_GITHUB_APP_URL;

export default function IntegrationsPage() {
  const { accessToken } = useAuth();
  const { activeOrgId, isLoading: orgLoading } = useActiveOrg();

  // Config form state
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [jql, setJql] = useState("issuetype = Bug");

  // Pull / file state
  const [project, setProject] = useState("");
  const [file, setFile] = useState<File | null>(null);

  // GitHub form state
  const [ghInstallId, setGhInstallId] = useState("");
  const [ghRepoFullName, setGhRepoFullName] = useState("");

  // Feedback state (Jira)
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ── orgs query (legacy: kept for orgId fallback) ───────────────────────────
  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgId = activeOrgId || orgsQuery.data?.[0]?.id || "";

  const queryClient = useQueryClient();

  // ── jira config query ───────────────────────────────────────────────────────
  const configQuery = useQuery({
    queryKey: ["jira-config", orgId],
    queryFn: () => getJiraConfig(accessToken!, orgId),
    enabled: Boolean(accessToken && orgId),
  });
  const configured = configQuery.data?.configured ?? false;

  // ── github config query ─────────────────────────────────────────────────────
  const githubConfigQuery = useQuery({
    queryKey: ["github-config", orgId],
    queryFn: () => getGithubConfig(accessToken!, { org_id: orgId }),
    enabled: Boolean(accessToken && orgId),
  });
  const githubConfigured = githubConfigQuery.data?.configured ?? false;

  // ── list repo tests query ───────────────────────────────────────────────────
  const repoTestsQuery = useQuery({
    queryKey: ["repo-tests", orgId],
    queryFn: () => listRepoTests(accessToken!, { org_id: orgId }),
    enabled: Boolean(accessToken && orgId),
  });
  const repoTests = repoTestsQuery.data ?? [];

  // ── save github config mutation ─────────────────────────────────────────────
  const saveGithubMut = useMutation({
    mutationFn: () =>
      saveGithubConfig(accessToken!, {
        org_id: orgId,
        installation_id: ghInstallId,
        repo_full_name: ghRepoFullName,
      }),
    onSuccess: () => {
      void githubConfigQuery.refetch();
      toast.success("Configuración de GitHub guardada.");
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // ── index repo mutation ─────────────────────────────────────────────────────
  const indexMut = useMutation({
    mutationFn: () => indexRepo(accessToken!, { org_id: orgId }),
    onSuccess: (data) => {
      toast.success(`${data.indexed} tests indexados`);
      void queryClient.invalidateQueries({ queryKey: ["repo-tests", orgId] });
    },
    onError: (err: Error) => {
      const msg =
        err instanceof ApiClientError && err.status === 503
          ? "Configura GitHub"
          : err.message;
      toast.error(msg);
    },
  });

  // ── helpers ─────────────────────────────────────────────────────────────────
  function clearFeedback() {
    setMsg(null);
    setError(null);
  }

  function showCounts(res: JiraIngestResponse) {
    setMsg(
      `Listo. Ingeridos: ${res.ingested} · Nuevos: ${res.novel} · Conocidos: ${res.known} · Omitidos: ${res.skipped}`,
    );
  }

  // ── save jira config ─────────────────────────────────────────────────────────
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

  // ── pull from API ─────────────────────────────────────────────────────────────
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

  // ── file upload ───────────────────────────────────────────────────────────────
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

  // ── domain counts from test list ──────────────────────────────────────────────
  const domainCounts = repoTests.reduce<Record<string, number>>((acc, t) => {
    return { ...acc, [t.domain]: (acc[t.domain] ?? 0) + 1 };
  }, {});

  if (orgLoading) {
    return (
      <div className="space-y-6" data-testid="integrations-loading-skeleton">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Integraciones</h1>
          <p className="text-sm text-zinc-500">Conecta GitHub y Jira para potenciar el análisis de QA.</p>
        </div>
        <Skeleton className="h-48 max-w-xl rounded-xl" />
        <Skeleton className="h-48 max-w-xl rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Integraciones</h1>
        <p className="text-sm text-zinc-500">Conecta GitHub y Jira para potenciar el análisis de QA.</p>
      </div>

      {/* ── GitHub config card ────────────────────────────────────────────── */}
      <Card className="max-w-xl space-y-4 p-5">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-zinc-700">Configuración de GitHub</h2>
          {githubConfigured && (
            <span
              data-testid="github-connected-badge"
              className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700"
            >
              ✓ Conectado
            </span>
          )}
        </div>
        <ol className="list-decimal space-y-1 pl-4 text-xs text-zinc-500">
          <li>
            Instala la GitHub App de Mnemo en tu organización
            {GITHUB_APP_URL ? (
              <>
                {" — "}
                <a
                  href={GITHUB_APP_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-zinc-700 underline underline-offset-2 hover:text-zinc-900"
                >
                  instalar ahora ↗
                </a>
              </>
            ) : (
              <> (GitHub → Settings → GitHub Apps)</>
            )}
            .
          </li>
          <li>
            Al terminar, GitHub te deja en una URL{" "}
            <code className="rounded bg-zinc-100 px-1">…/installations/12345678</code>: ese
            número es el <strong>Installation ID</strong>.
          </li>
          <li>Pégalo aquí junto al repositorio y guarda.</li>
        </ol>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="gh-install-id">Installation ID</Label>
            <Input
              id="gh-install-id"
              aria-describedby="gh-install-id-hint"
              value={ghInstallId}
              onChange={(e) => setGhInstallId(e.target.value)}
              placeholder="12345678"
            />
            <p
              id="gh-install-id-hint"
              data-testid="gh-install-id-hint"
              className="text-xs text-zinc-400"
            >
              El número final de la URL de instalación (ej. 12345678).
            </p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="gh-repo">Repositorio (owner/repo)</Label>
            <Input
              id="gh-repo"
              aria-describedby="gh-repo-hint"
              value={ghRepoFullName}
              onChange={(e) => setGhRepoFullName(e.target.value)}
              placeholder="mi-empresa/mi-repo"
            />
            <p
              id="gh-repo-hint"
              data-testid="gh-repo-hint"
              className="text-xs text-zinc-400"
            >
              Formato: <code>owner/nombre</code> (ej. mi-empresa/mi-repo).
            </p>
          </div>
          {githubConfigured && githubConfigQuery.data?.repo_full_name && (
            <p className="text-xs text-zinc-500">
              Repositorio configurado: <strong>{githubConfigQuery.data.repo_full_name}</strong>. Rellena los campos para actualizar.
            </p>
          )}
          <Button
            onClick={() => saveGithubMut.mutate()}
            disabled={saveGithubMut.isPending || !ghInstallId || !ghRepoFullName}
          >
            {saveGithubMut.isPending ? "Guardando…" : "Guardar configuración de GitHub"}
          </Button>
        </div>
      </Card>

      {/* ── Repo indexing card ────────────────────────────────────────────── */}
      <Card className="max-w-xl space-y-4 p-5">
        <h2 className="text-sm font-medium text-zinc-700">Tests del repositorio</h2>

        <div className="space-y-2">
          <Button
            onClick={() => indexMut.mutate()}
            disabled={indexMut.isPending || !githubConfigured}
          >
            {indexMut.isPending ? "Indexando…" : "Indexar tests del repo"}
          </Button>
          {!githubConfigured && (
            <p className="text-xs text-zinc-500">configura GitHub primero</p>
          )}
        </div>

        {repoTests.length > 0 && (
          <div className="space-y-3 border-t pt-4">
            <div className="flex flex-wrap gap-2">
              {Object.entries(domainCounts).map(([domain, count]) => (
                <span
                  key={domain}
                  className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-700"
                >
                  {domain}: {count}
                </span>
              ))}
            </div>
            <ul className="space-y-1">
              {repoTests.map((t) => (
                <li key={t.path} className="text-xs text-zinc-600">
                  <span className="font-mono">{t.path}</span>
                  {" · "}
                  <span className="text-zinc-400">{t.framework}</span>
                  {" · "}
                  <span className="text-zinc-400">{t.domain}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* ── Jira config card ──────────────────────────────────────────────── */}
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

      {/* ── Import card ───────────────────────────────────────────────────── */}
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
          <FileDropzone
            id="export-file"
            file={file}
            onFile={setFile}
            accept=".csv,.json"
            hint="Export de issues de Jira en CSV o JSON"
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
