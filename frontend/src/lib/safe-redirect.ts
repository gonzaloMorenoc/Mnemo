/**
 * Validación del parámetro `?next=` del login/registro (hallazgo #16, F13).
 *
 * Solo se aceptan rutas internas: empiezan por una única "/" y no contienen
 * nada que un navegador pueda interpretar como otro origen ("//", "/\", "\\",
 * caracteres de control o sus versiones codificadas).
 */
export const DEFAULT_AFTER_LOGIN = "/app/continuity";

// Caracteres de control (los navegadores eliminan \t \n \r, lo que convertiría
// "/\t/evil" en "//evil") y la barra invertida (algunos la tratan como "/").
const UNSAFE_CHARS = /[\u0000-\u001f\u007f\\]/;

function decodeSafely(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

function isInternalPath(value: string): boolean {
  if (!value.startsWith("/") || value.startsWith("//")) return false;
  return !UNSAFE_CHARS.test(value);
}

export function safeNextPath(
  raw: string | null | undefined,
  fallback: string = DEFAULT_AFTER_LOGIN,
): string {
  if (!raw) return fallback;
  const decoded = decodeSafely(raw);
  if (decoded === null) return fallback;
  return isInternalPath(raw) && isInternalPath(decoded) ? raw : fallback;
}
