"use client";

import { useState } from "react";

import { getGithubInstallUrl } from "@/lib/api/endpoints";
import {
  REPO_FULL_NAME_PATTERN,
  githubLinkErrorMessage,
  redirectTo,
  savePendingGithubLink,
} from "@/lib/github/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Target = "install" | "authorize";

/**
 * Inicio de la vinculación de GitHub con prueba de posesión: pide al backend la URL
 * con el `state` firmado y manda al usuario a GitHub. El callback termina el alta.
 */
export function GithubConnectButton({
  accessToken,
  orgId,
  initialRepo = "",
}: {
  accessToken: string | null;
  orgId: string;
  initialRepo?: string;
}) {
  const [repo, setRepo] = useState(initialRepo);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const repoTrimmed = repo.trim();
  const repoValid = REPO_FULL_NAME_PATTERN.test(repoTrimmed);

  async function connect(target: Target) {
    setError(null);
    if (!accessToken || !orgId) {
      setError("No se encontró la organización activa.");
      return;
    }
    if (!repoValid) {
      setError("Indica el repositorio con el formato owner/nombre.");
      return;
    }
    setPending(true);
    try {
      const res = await getGithubInstallUrl(accessToken, { org_id: orgId });
      savePendingGithubLink({ orgId, repoFullName: repoTrimmed, state: res.state });
      redirectTo(target === "install" ? res.install_url : res.authorize_url);
    } catch (err) {
      setError(githubLinkErrorMessage(err));
      setPending(false);
    }
  }

  return (
    <div className="space-y-4">
      <ol className="list-decimal space-y-1 pl-4 text-xs text-zinc-500">
        <li>Indica el repositorio que quieres conectar.</li>
        <li>
          Pulsa «Conectar con GitHub»: instala la App de Mnemo en la cuenta del
          repositorio y autoriza el acceso.
        </li>
        <li>GitHub te devuelve aquí y la conexión queda guardada.</li>
      </ol>
      <div className="space-y-1">
        <Label htmlFor="gh-repo">Repositorio (owner/repo)</Label>
        <Input
          id="gh-repo"
          aria-describedby="gh-repo-hint"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="mi-empresa/mi-repo"
        />
        <p id="gh-repo-hint" data-testid="gh-repo-hint" className="text-xs text-zinc-500">
          Formato: <code>owner/nombre</code> (ej. mi-empresa/mi-repo).
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => void connect("install")} disabled={pending || !repoValid}>
          {pending ? "Redirigiendo a GitHub…" : "Conectar con GitHub"}
        </Button>
        <button
          type="button"
          onClick={() => void connect("authorize")}
          disabled={pending || !repoValid}
          className="text-xs font-medium text-zinc-600 underline underline-offset-2 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          ¿La App ya está instalada? Solo autorizar
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
