import type { ApiErrorShape } from "@/lib/api/types";

export class ApiClientError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.details = details;
  }
}

interface ApiRequestOptions {
  token?: string | null;
  body?: BodyInit | Record<string, unknown>;
  headers?: HeadersInit;
  cache?: RequestCache;
}

export async function apiRequest<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "DELETE",
  options: ApiRequestOptions = {},
) {
  const headers = new Headers(options.headers ?? {});

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  let body: BodyInit | undefined;
  if (options.body instanceof FormData || options.body instanceof URLSearchParams || typeof options.body === "string") {
    body = options.body;
  } else if (options.body) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const response = await fetch(path, {
    method,
    headers,
    body,
    cache: options.cache ?? "no-store",
  });

  const text = await response.text();
  const parsed = text ? safeJsonParse(text) : null;

  if (!response.ok) {
    const message = errorMessage(response.status, parsed as ApiErrorShape | null);
    throw new ApiClientError(message, response.status, parsed ?? text);
  }

  return parsed as T;
}

/**
 * El mensaje que verá una persona (va a toasts y avisos). Un 4xx con texto del
 * backend lo conserva: son mensajes de negocio («proyecto no encontrado…»). Un 5xx
 * no enseña el texto interno («Database error»). Y un 422 de validación trae una
 * LISTA en `detail`, que acababa pintado como «[object Object]». El cuerpo original
 * sigue en `details` para quien lo necesite.
 */
function errorMessage(status: number, payload: ApiErrorShape | null): string {
  if (status >= 500) {
    return `El servidor no ha podido completar la acción (error ${status}). Inténtalo de nuevo en unos segundos.`;
  }
  const detail: unknown = payload?.detail ?? payload?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (status === 422) return "Hay datos que no son válidos. Revisa el formulario.";
  return `No se pudo completar la acción (error ${status}).`;
}

function safeJsonParse(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
