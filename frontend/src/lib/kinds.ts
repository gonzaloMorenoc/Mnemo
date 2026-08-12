/**
 * Tipos de conocimiento — única fuente de verdad del frontend.
 *
 * Los 7 primeros describen el PRODUCTO y sus fallos. Los 4 últimos son el OFICIO
 * del proyecto (auditoría 12-ago, H3): lo que se va con el QA senior y antes no
 * tenía dónde vivir. Debe coincidir con `_KINDS` (src/knowledge/repository.py) y
 * con el CHECK de la migración 027.
 */
export const KIND_ORDER = [
  "regla_negocio",
  "flujo",
  "riesgo",
  "glosario",
  "leccion",
  "reto",
  "patron",
  "runbook",
  "dato_prueba",
  "contacto",
  "decision",
] as const;

export type KindValue = (typeof KIND_ORDER)[number];

export const KIND_LABEL: Record<KindValue, string> = {
  regla_negocio: "Regla de negocio",
  flujo: "Flujo",
  riesgo: "Riesgo",
  glosario: "Glosario",
  leccion: "Lección",
  reto: "Reto",
  patron: "Patrón",
  runbook: "Runbook",
  dato_prueba: "Dato de prueba",
  contacto: "Contacto",
  decision: "Decisión",
};

export const KIND_OPTIONS = KIND_ORDER.map((value) => ({
  value,
  label: KIND_LABEL[value],
}));

/**
 * Etiqueta de un kind que llega del API como `string` (y por tanto podría ser uno
 * que este frontend aún no conoce, p. ej. tras desplegar el backend antes). Se
 * devuelve el valor crudo en vez de "undefined": peor es mentir que quedarse corto.
 */
export function kindLabel(kind: string): string {
  return KIND_LABEL[kind as KindValue] ?? kind;
}

/** Pista de redacción por tipo. Solo la llevan los que se prestan a confusión. */
export const KIND_HINT: Partial<Record<KindValue, string>> = {
  runbook: "Pasos reproducibles: cómo levantar el entorno, lanzar la suite, restaurar datos.",
  dato_prueba: "Usuarios, tarjetas o datasets con los que se prueba. Nunca credenciales reales.",
  contacto: "Equipos y canales, no personas: «el sandbox del PSP lo lleva Pagos — #pagos-soporte».",
  decision: "Qué se acordó, con quién y por qué. Sobre todo lo que se decidió NO hacer.",
};

// Aviso suave, no validación: un buzón compartido (soporte@) es legítimo y no es un
// dato personal, así que esto NUNCA bloquea el guardado. El backend ya redacta los
// emails del contenido importado (src/sanitizer.py); el alta manual no, a propósito.
const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/;

export function looksLikePersonalEmail(text: string): boolean {
  return EMAIL_RE.test(text);
}
