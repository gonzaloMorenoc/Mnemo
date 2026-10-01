/**
 * Datos del acta tal y como se muestran en el sello de /verify. Lo firmado no
 * cambia: solo cómo se lee (antes: ISO con microsegundos y commits cortados aunque
 * no fueran un SHA, p. ej. «demo-real-00»).
 */
const SHA = /^[0-9a-f]{12,64}$/i;

export function refCommit(value: string): string {
  return SHA.test(value) ? value.slice(0, 12) : value;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
  "septiembre", "octubre", "noviembre", "diciembre"];

// Construida a mano y no con toLocaleString: el texto de Intl cambia con la versión
// de ICU («…de 2026, 16:46» en Node, «…de 2026 a las 16:46» en Chrome).
export function fechaActa(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${d.getUTCDate()} de ${MESES[d.getUTCMonth()]} de ${d.getUTCFullYear()}, ${hh}:${mm} UTC`;
}
