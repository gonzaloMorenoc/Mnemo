import { ApiClientError } from "@/lib/api/client";

/**
 * Vinculación de la GitHub App con prueba de posesión (PR #137).
 *
 * 1. Integraciones pide `install-url` (state firmado, 10 min) y redirige a GitHub.
 * 2. GitHub vuelve a /app/integrations/github/callback con installation_id, code y state.
 * 3. El callback manda todo a POST /v2/integrations/github.
 *
 * El repositorio y la org no viajan por GitHub: se guardan en sessionStorage antes
 * de salir y el callback los recupera (solo comodidad; el backend lo valida todo).
 */

export const GITHUB_CALLBACK_PATH = "/app/integrations/github/callback";
export const INTEGRATIONS_PATH = "/app/integrations";
export const REPO_FULL_NAME_PATTERN = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;

const PENDING_KEY = "mnemo:github-link:pending";

export interface PendingGithubLink {
  readonly orgId: string;
  readonly repoFullName: string;
  readonly state: string;
}

function isPendingGithubLink(value: unknown): value is PendingGithubLink {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.orgId === "string" &&
    typeof v.repoFullName === "string" &&
    typeof v.state === "string"
  );
}

export function savePendingGithubLink(link: PendingGithubLink): void {
  try {
    window.sessionStorage.setItem(PENDING_KEY, JSON.stringify(link));
  } catch {
    // Sin almacenamiento (modo privado): el callback pedirá el repositorio a mano.
  }
}

export function readPendingGithubLink(): PendingGithubLink | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isPendingGithubLink(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function clearPendingGithubLink(): void {
  try {
    window.sessionStorage.removeItem(PENDING_KEY);
  } catch {
    // Nada que limpiar si no hay almacenamiento.
  }
}

/** Redirección completa del navegador (a GitHub). Aislada para poder simularla en tests. */
export function redirectTo(url: string): void {
  window.location.assign(url);
}

const MSG_STATE_EXPIRED =
  "El enlace de vinculación ha caducado (dura 10 minutos). Vuelve a Integraciones y pulsa «Conectar con GitHub» otra vez.";
const MSG_STATE_FOREIGN =
  "Esta vinculación la inició otra organización u otro usuario. Iníciala de nuevo desde Integraciones con tu cuenta.";
const MSG_STATE_INVALID =
  "El enlace de vinculación no es válido. Vuelve a iniciarla desde Integraciones.";
const MSG_NO_ACCESS =
  "Tu usuario de GitHub no tiene acceso a esa instalación de la App. Pide acceso a un administrador de la organización de GitHub o instala la App tú mismo.";
const MSG_ALREADY_BOUND =
  "Esa instalación de GitHub ya está vinculada a otra organización de Mnemo. Desvincúlala allí antes de conectarla aquí.";
const MSG_REPO_MISMATCH =
  "El repositorio no pertenece a la cuenta donde está instalada la App. Revisa el owner/repo.";
const MSG_NOT_CONFIGURED =
  "La GitHub App no está configurada en el servidor. Avisa al administrador de Mnemo.";
const MSG_MISSING_PROOF =
  "GitHub no devolvió la autorización. Vuelve a iniciar la vinculación desde Integraciones.";
const MSG_FORBIDDEN =
  "No tienes permiso para vincular GitHub en esta organización (hace falta ser owner o admin).";
const MSG_GENERIC = "No se pudo vincular GitHub. Inténtalo de nuevo.";

function messageFor403(detail: string): string {
  const d = detail.toLowerCase();
  if (d.includes("caducado")) return MSG_STATE_EXPIRED;
  if (d.includes("otra organización") || d.includes("otro usuario")) return MSG_STATE_FOREIGN;
  if (d.includes("state")) return MSG_STATE_INVALID;
  if (d.includes("acceso")) return MSG_NO_ACCESS;
  if (d.includes("no pertenece")) return MSG_REPO_MISMATCH;
  if (d.includes("instalación")) return MSG_NO_ACCESS;
  return MSG_FORBIDDEN;
}

/** Traduce el error del backend a un mensaje claro en español para la UI. */
export function githubLinkErrorMessage(err: unknown): string {
  if (!(err instanceof ApiClientError)) {
    return err instanceof Error && err.message ? err.message : MSG_GENERIC;
  }
  switch (err.status) {
    case 400:
      return err.message.toLowerCase().includes("state") ? MSG_MISSING_PROOF : err.message;
    case 403:
      return messageFor403(err.message);
    case 409:
      return MSG_ALREADY_BOUND;
    case 503:
      return MSG_NOT_CONFIGURED;
    default:
      return err.message || MSG_GENERIC;
  }
}
