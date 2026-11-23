import { describe, expect, it } from "vitest";

import { ApiClientError } from "@/lib/api/client";
import {
  isTransientError,
  MAX_TRANSIENT_RETRIES,
  queryRetryDelay,
  shouldRetryQuery,
} from "@/lib/api/retry";

describe("política de reintentos (arranque en frío del backend)", () => {
  it("502/503/504 y fallos de red son transitorios", () => {
    for (const status of [502, 503, 504]) {
      expect(isTransientError(new ApiClientError("x", status))).toBe(true);
    }
    expect(isTransientError(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("un 4xx o un 500 no son transitorios", () => {
    for (const status of [400, 401, 403, 404, 413, 422, 500]) {
      expect(isTransientError(new ApiClientError("x", status))).toBe(false);
    }
  });

  it("reintenta los transitorios varias veces mientras el servidor despierta", () => {
    expect(shouldRetryQuery(0, new ApiClientError("x", 504))).toBe(true);
    expect(shouldRetryQuery(MAX_TRANSIENT_RETRIES - 1, new ApiClientError("x", 502))).toBe(true);
    expect(shouldRetryQuery(MAX_TRANSIENT_RETRIES, new ApiClientError("x", 502))).toBe(false);
  });

  it("no reintenta errores del cliente (404, 401, 422)", () => {
    expect(shouldRetryQuery(0, new ApiClientError("x", 404))).toBe(false);
    expect(shouldRetryQuery(0, new ApiClientError("x", 401))).toBe(false);
    expect(shouldRetryQuery(0, new ApiClientError("x", 422))).toBe(false);
  });

  it("un 500 se reintenta una sola vez", () => {
    expect(shouldRetryQuery(0, new ApiClientError("x", 500))).toBe(true);
    expect(shouldRetryQuery(1, new ApiClientError("x", 500))).toBe(false);
  });

  it("la espera crece y tiene techo", () => {
    expect(queryRetryDelay(0)).toBeLessThan(queryRetryDelay(1));
    expect(queryRetryDelay(1)).toBeLessThan(queryRetryDelay(2));
    expect(queryRetryDelay(20)).toBe(queryRetryDelay(30));
  });
});
