/**
 * Enlace de verificación autocontenido: el acta viaja en el FRAGMENTO de la URL
 * (no llega al servidor, no queda en logs de acceso).
 *
 * Los bytes los emite el backend (`share_blob`); aquí solo se transportan y se
 * decodifican verbatim. Nunca se re-serializa el acta en JavaScript:
 * `JSON.parse` + `JSON.stringify` colapsa `0.0` a `0` y rompería la firma.
 */

const PREFIX = "#v1.";
// 4x el umbral del backend (MAX_SHARE_BYTES = 8192), con holgura por si sube.
// El fragmento lo controla quien envía el enlace: no decodificamos 10 MB.
const MAX_HASH_CHARS = 32768;

export function buildShareUrl(origin: string, share: string): string {
  return `${origin}/verify${PREFIX}${share}`;
}

export function decodeShare(hash: string): string | null {
  if (!hash.startsWith(PREFIX)) return null;
  const blob = hash.slice(PREFIX.length);
  if (!blob || blob.length > MAX_HASH_CHARS) return null;
  try {
    const padded = blob + "=".repeat((4 - (blob.length % 4)) % 4);
    // atob solo como paso a BYTES; su salida nunca se trata como texto.
    const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const texto = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return texto.trimStart().startsWith("{") ? texto : null;
  } catch {
    return null;
  }
}
