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
    const errorPayload = parsed as ApiErrorShape | null;
    const message =
      errorPayload?.detail ??
      errorPayload?.message ??
      `Request failed with status ${response.status}`;
    throw new ApiClientError(message, response.status, parsed ?? text);
  }

  return parsed as T;
}

function safeJsonParse(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
