import { describe, expect, it } from "vitest";

import { buildShareUrl, decodeShare } from "@/lib/certificate-share";

// Un acta como la que emite el backend: float redondo + acentos.
const ACTA =
  '{"canonical_json":{"schema":"mnemo.cert.v3","disclaimer":"evaluación asistida","x":0.0},"signature":"sig"}';
// Buffer hace aquí de backend (share_blob): base64url sin padding.
const BLOB = Buffer.from(ACTA, "utf8").toString("base64url").replace(/=+$/, "");

describe("certificate-share", () => {
  it("construye el enlace a la página pública con prefijo de versión", () => {
    expect(buildShareUrl("https://mnemo.app", BLOB)).toBe(`https://mnemo.app/verify#v1.${BLOB}`);
  });

  it("decodifica el acta VERBATIM: el 0.0 y los acentos sobreviven", () => {
    const texto = decodeShare(`#v1.${BLOB}`);
    expect(texto).toBe(ACTA);
    expect(texto).toContain('"x":0.0');
    expect(texto).toContain("evaluación");
  });

  it("ignora un hash sin el prefijo de versión", () => {
    expect(decodeShare(`#${BLOB}`)).toBeNull();
    expect(decodeShare("#v2.abc")).toBeNull();
    expect(decodeShare("")).toBeNull();
  });

  it("devuelve null con base64 inválido, sin lanzar", () => {
    expect(decodeShare("#v1.@@@@")).toBeNull();
  });

  it("rechaza un hash sobredimensionado sin decodificarlo", () => {
    expect(decodeShare(`#v1.${"A".repeat(40000)}`)).toBeNull();
  });
});
