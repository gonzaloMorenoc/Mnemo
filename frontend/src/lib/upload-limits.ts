/**
 * Límite de subida por el navegador (hallazgo F9). Las subidas pasan por un route
 * handler de Vercel, que corta el cuerpo de la petición en ~4,5 MB; el multipart
 * añade algo de cabecera, así que el máximo útil del archivo es 4 MB.
 */
export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

const BYTES_PER_MB = 1024 * 1024;
const MAX_UPLOAD_LABEL = `${MAX_UPLOAD_BYTES / BYTES_PER_MB} MB`;
const LARGE_REPORT_HINT =
  "Para informes grandes, envíalos desde el CI con un token de ingesta (Integraciones).";

function formatMb(bytes: number): string {
  // Redondeo hacia arriba: 4 MB + 1 byte no puede leerse como «pesa 4 MB».
  const tenths = Math.ceil((bytes / BYTES_PER_MB) * 10) / 10;
  return `${tenths.toLocaleString("es-ES", { maximumFractionDigits: 1 })} MB`;
}

export function uploadTooLargeMessage(bytes?: number): string {
  const size = bytes === undefined ? "El archivo es demasiado grande" : `El archivo pesa ${formatMb(bytes)}`;
  return `${size}: el máximo por subida es ${MAX_UPLOAD_LABEL}. ${LARGE_REPORT_HINT}`;
}

export function exceedsUploadLimit(bytes: number, maxBytes: number = MAX_UPLOAD_BYTES): boolean {
  return bytes > maxBytes;
}
