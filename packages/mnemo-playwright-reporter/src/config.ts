import { MnemoConfig } from "./types";

export interface MnemoOptions {
  url?: string;
  secret?: string;
  orgId?: string;
  project?: string;
  commitSha?: string;
  runUid?: string;
}

type Env = Record<string, string | undefined>;

/** run_uid para la dedup del backend: opción > MNEMO_RUN_UID > run de GitHub Actions.
 *  El fallback gh-<run_id>-<attempt> hace que re-entregar el mismo job no duplique el run. */
function resolveRunUid(env: Env, options: MnemoOptions): string | null {
  if (options.runUid) return options.runUid;
  if (env.MNEMO_RUN_UID) return env.MNEMO_RUN_UID;
  if (env.GITHUB_RUN_ID) return `gh-${env.GITHUB_RUN_ID}-${env.GITHUB_RUN_ATTEMPT ?? "1"}`;
  return null;
}

/** Resuelve la config desde opciones (prioridad) y env. Devuelve null si falta algo requerido. */
export function resolveConfig(env: Env, options: MnemoOptions = {}): MnemoConfig | null {
  const url = options.url ?? env.MNEMO_WEBHOOK_URL;
  const secret = options.secret ?? env.MNEMO_WEBHOOK_SECRET;
  const orgId = options.orgId ?? env.MNEMO_ORG_ID;
  const project = options.project ?? env.MNEMO_PROJECT;
  const commitSha = options.commitSha ?? env.MNEMO_COMMIT_SHA ?? env.GITHUB_SHA;
  if (!url || !secret || !orgId || !project || !commitSha) return null;
  return { url, secret, orgId, project, commitSha, runUid: resolveRunUid(env, options) };
}
