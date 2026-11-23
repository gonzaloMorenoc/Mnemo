"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { saveGithubConfig } from "@/lib/api/endpoints";
import {
  INTEGRATIONS_PATH,
  REPO_FULL_NAME_PATTERN,
  clearPendingGithubLink,
  githubLinkErrorMessage,
  readPendingGithubLink,
} from "@/lib/github/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Tras vincular, volvemos solos a Integraciones (con enlace por si acaso).
export const SUCCESS_REDIRECT_MS = 2500;

const MSG_NO_AUTH =
  "GitHub no devolvió la autorización (falta code o state). Comprueba que la App tiene activado «Request user authorization (OAuth) during installation» y vuelve a iniciar la vinculación desde Integraciones.";
const MSG_STATE_MISMATCH =
  "Esta respuesta de GitHub no corresponde a la vinculación iniciada en este navegador. Vuelve a iniciarla desde Integraciones.";
const MSG_REQUESTED =
  "GitHub ha enviado la solicitud de instalación a un administrador de la cuenta. Cuando la apruebe, vuelve a Integraciones y pulsa «Conectar con GitHub».";

export interface GithubCallbackParams {
  readonly installationId: string;
  readonly code: string;
  readonly state: string;
  readonly setupAction: string;
}

type Phase =
  | { kind: "form" }
  | { kind: "submitting" }
  | { kind: "success"; repo: string }
  | { kind: "error"; message: string }
  | { kind: "info"; message: string };

function initialPhase(params: GithubCallbackParams, pendingState: string | null): Phase {
  if (params.setupAction === "request") return { kind: "info", message: MSG_REQUESTED };
  if (!params.code || !params.state) return { kind: "error", message: MSG_NO_AUTH };
  if (pendingState !== null && pendingState !== params.state) {
    return { kind: "error", message: MSG_STATE_MISMATCH };
  }
  return { kind: "form" };
}

export function GithubCallbackView({ params }: { params: GithubCallbackParams }) {
  const { accessToken } = useAuth();
  const { activeOrgId } = useActiveOrg();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [pending] = useState(() => readPendingGithubLink());
  const [phase, setPhase] = useState<Phase>(() => initialPhase(params, pending?.state ?? null));
  const [repo, setRepo] = useState(pending?.repoFullName ?? "");
  const [installationId, setInstallationId] = useState(params.installationId);
  // El `code` de GitHub es de un solo uso: nunca lo mandamos dos veces.
  const submitted = useRef(false);

  const orgId = pending?.orgId ?? activeOrgId ?? "";
  const ready =
    Boolean(accessToken && orgId) &&
    REPO_FULL_NAME_PATTERN.test(repo.trim()) &&
    installationId.trim() !== "";

  async function submit() {
    if (submitted.current || !accessToken) return;
    submitted.current = true;
    setPhase({ kind: "submitting" });
    const repoFullName = repo.trim();
    try {
      await saveGithubConfig(accessToken, {
        org_id: orgId,
        installation_id: installationId.trim(),
        repo_full_name: repoFullName,
        state: params.state,
        code: params.code,
      });
      clearPendingGithubLink();
      void queryClient.invalidateQueries({ queryKey: ["github-config", orgId] });
      setPhase({ kind: "success", repo: repoFullName });
    } catch (err) {
      setPhase({ kind: "error", message: githubLinkErrorMessage(err) });
    }
  }

  // Si GitHub y el navegador nos dieron todo, completamos el alta sin clics.
  // Solo depende de que el token esté listo: el resto viene de la URL o del arranque.
  useEffect(() => {
    if (phase.kind === "form" && ready && Boolean(pending)) void submit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  useEffect(() => {
    if (phase.kind !== "success") return;
    const timer = setTimeout(() => router.replace(INTEGRATIONS_PATH), SUCCESS_REDIRECT_MS);
    return () => clearTimeout(timer);
  }, [phase.kind, router]);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Conectar GitHub</h1>
      <Card className="max-w-xl space-y-4 p-6">
        <PhaseBody
          phase={phase}
          form={
            <ManualForm
              repo={repo}
              onRepo={setRepo}
              installationId={installationId}
              onInstallationId={params.installationId ? undefined : setInstallationId}
              disabled={!ready}
              onSubmit={() => void submit()}
            />
          }
        />
        {phase.kind !== "submitting" && (
          <Link
            href={INTEGRATIONS_PATH}
            className="inline-block text-sm font-medium text-zinc-700 underline underline-offset-2 hover:text-zinc-900"
          >
            Volver a Integraciones
          </Link>
        )}
      </Card>
    </div>
  );
}

function PhaseBody({ phase, form }: { phase: Phase; form: React.ReactNode }) {
  switch (phase.kind) {
    case "submitting":
      return <p className="text-sm text-zinc-600">Vinculando la instalación de GitHub…</p>;
    case "success":
      return (
        <p role="status" className="text-sm text-green-700">
          GitHub conectado: <strong>{phase.repo}</strong>. Te llevamos a Integraciones…
        </p>
      );
    case "error":
      return (
        <p role="alert" className="text-sm text-red-600">
          {phase.message}
        </p>
      );
    case "info":
      return (
        <p role="status" className="text-sm text-zinc-700">
          {phase.message}
        </p>
      );
    default:
      return <>{form}</>;
  }
}

function ManualForm({
  repo,
  onRepo,
  installationId,
  onInstallationId,
  disabled,
  onSubmit,
}: {
  repo: string;
  onRepo: (v: string) => void;
  installationId: string;
  onInstallationId?: (v: string) => void;
  disabled: boolean;
  onSubmit: () => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-600">
        GitHub ha autorizado el acceso. Completa los datos para terminar la conexión.
      </p>
      <div className="space-y-1">
        <Label htmlFor="gh-callback-repo">Repositorio (owner/repo)</Label>
        <Input
          id="gh-callback-repo"
          value={repo}
          onChange={(e) => onRepo(e.target.value)}
          placeholder="mi-empresa/mi-repo"
        />
      </div>
      {onInstallationId && (
        <div className="space-y-1">
          <Label htmlFor="gh-callback-installation">Installation ID</Label>
          <Input
            id="gh-callback-installation"
            value={installationId}
            onChange={(e) => onInstallationId(e.target.value)}
            placeholder="12345678"
          />
          <p className="text-xs text-zinc-500">
            El número final de github.com/settings/installations/12345678.
          </p>
        </div>
      )}
      <Button onClick={onSubmit} disabled={disabled}>
        Terminar conexión
      </Button>
    </div>
  );
}
