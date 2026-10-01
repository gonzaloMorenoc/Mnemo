import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * El acta de traspaso María → Pablo de la demo, emitida en producción el
 * 1-oct-2026 (`mnemo.traspaso.v2`). Una acta firmada no caduca: sigue siendo
 * válida aunque se re-siembre la demo o se rote la clave (anillo por key_id).
 */
export const ACTA_TRASPASO_HASH = readFileSync(
  path.join(__dirname, "fixtures", "acta-traspaso-demo.hash"),
  "utf8",
).trim();

const PREFIX = "#v1.";

function decode(hash: string): { canonical_json: Record<string, unknown>; signature: string } {
  return JSON.parse(Buffer.from(hash.slice(PREFIX.length), "base64url").toString("utf8"));
}

/** El mismo enlace con el contenido retocado y la firma original: debe fallar. */
export function manipular(hash: string, cambios: Record<string, unknown>): string {
  const acta = decode(hash);
  const retocada = { ...acta, canonical_json: { ...acta.canonical_json, ...cambios } };
  return PREFIX + Buffer.from(JSON.stringify(retocada), "utf8").toString("base64url");
}

export function contenidoDe(hash: string): Record<string, unknown> {
  return decode(hash).canonical_json;
}
