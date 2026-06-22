import { MnemoConfig } from "./types";

export interface MnemoOptions {
  url?: string;
  secret?: string;
  orgId?: string;
  project?: string;
  commitSha?: string;
}

type Env = Record<string, string | undefined>;

/** Resuelve la config desde opciones (prioridad) y env. Devuelve null si falta algo requerido. */
export function resolveConfig(env: Env, options: MnemoOptions = {}): MnemoConfig | null {
  const url = options.url ?? env.MNEMO_WEBHOOK_URL;
  const secret = options.secret ?? env.MNEMO_WEBHOOK_SECRET;
  const orgId = options.orgId ?? env.MNEMO_ORG_ID;
  const project = options.project ?? env.MNEMO_PROJECT;
  const commitSha = options.commitSha ?? env.MNEMO_COMMIT_SHA ?? env.GITHUB_SHA;
  if (!url || !secret || !orgId || !project || !commitSha) return null;
  return { url, secret, orgId, project, commitSha };
}
