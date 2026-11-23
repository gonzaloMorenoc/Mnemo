import { ApiClientError } from "@/lib/api/client";

/**
 * Reintentos de TanStack Query pensados para el arranque en frío del backend
 * (~1 min, hallazgo F5): un 502/504 o un fallo de red casi siempre significa
 * «el servidor está despertando», no «no hay datos». Un 4xx nunca se reintenta.
 */
export const MAX_TRANSIENT_RETRIES = 4;
const MAX_OTHER_RETRIES = 1;
const BASE_DELAY_MS = 2_000;
const MAX_DELAY_MS = 15_000;
const TRANSIENT_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

export function isTransientError(error: unknown): boolean {
  if (error instanceof ApiClientError) return TRANSIENT_STATUSES.has(error.status);
  // fetch rechaza con TypeError cuando no hay red o el proxy no responde.
  return error instanceof TypeError;
}

function isClientError(error: unknown): boolean {
  return error instanceof ApiClientError && error.status >= 400 && error.status < 500;
}

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (isTransientError(error)) return failureCount < MAX_TRANSIENT_RETRIES;
  if (isClientError(error)) return false;
  return failureCount < MAX_OTHER_RETRIES;
}

export function queryRetryDelay(attemptIndex: number): number {
  return Math.min(BASE_DELAY_MS * 2 ** attemptIndex, MAX_DELAY_MS);
}
