import { createHmac } from "crypto";

/** Firma HMAC-SHA256 del cuerpo (mismo algoritmo que verify_signature del backend). */
export function sign(body: string, secret: string): string {
  return "sha256=" + createHmac("sha256", secret).update(body, "utf8").digest("hex");
}
