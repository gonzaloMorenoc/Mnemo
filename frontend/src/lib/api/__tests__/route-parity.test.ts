import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Paridad de contrato: cada path `/api/*` que el frontend invoca desde
 * endpoints.ts DEBE tener su route handler (`route.ts`) en src/app/api.
 * Sin este handler, Next devuelve 404 en runtime aunque el backend implemente
 * el endpoint. Los segmentos dinámicos se normalizan a `:param` (Next casa por
 * posición, no por nombre).
 */

const PARAM = ":param";

function normalize(rawPath: string): string {
  // quita querystring y normaliza los `${...}` a un segmento comodín
  const noQuery = rawPath.split("?")[0];
  return noQuery.replace(/\$\{[^}]*\}/g, PARAM).replace(/\/+$/, "");
}

function requiredPaths(): string[] {
  const source = fs.readFileSync(
    path.join(process.cwd(), "src/lib/api/endpoints.ts"),
    "utf8",
  );
  const matches = source.matchAll(/["'`](\/api\/(?:v2|health)[^"'`?]*)/g);
  const set = new Set<string>();
  for (const m of matches) {
    set.add(normalize(m[1]));
  }
  return [...set].sort();
}

function existingRoutePatterns(): Set<string> {
  const apiRoot = path.join(process.cwd(), "src/app/api");
  const patterns = new Set<string>();

  function walk(dir: string) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.name === "route.ts") {
        const rel = path.relative(path.join(process.cwd(), "src/app"), dir);
        const pattern =
          "/" + rel.split(path.sep).map((seg) => (seg.startsWith("[") ? PARAM : seg)).join("/");
        patterns.add(pattern);
      }
    }
  }

  walk(apiRoot);
  return patterns;
}

describe("paridad endpoints.ts ↔ route handlers", () => {
  it("cada endpoint invocado tiene su route.ts (si no, 404 en runtime)", () => {
    const existing = existingRoutePatterns();
    const missing = requiredPaths().filter((p) => !existing.has(p));
    expect(missing, `Faltan route handlers para: ${missing.join(", ")}`).toEqual([]);
  });
});
