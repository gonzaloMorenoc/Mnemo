import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "continuidad",
  title: "Continuidad y acta de traspaso",
  summary: "Cuánto sabe Mnemo de cada proyecto y cómo se firma un traspaso.",
  sections: [
    {
      heading: "El índice de continuidad",
      blocks: [
        {
          kind: "p",
          text: "En [Continuidad](/app/continuity) cada proyecto tiene un índice de 0 a 100: cuánto de él sabe Mnemo. No es una opinión, es un recuento con cuatro partes que ves por separado:",
        },
        {
          kind: "list",
          items: [
            "**Memoria de defectos:** familias de fallos del proyecto que ya tienen conocimiento asociado.",
            "**El porqué de las etiquetas:** familias etiquetadas con una razón escrita.",
            "**Oficio del proyecto:** si hay runbooks, datos de prueba, contactos y decisiones documentados.",
            "**Reglas con respaldo:** reglas y riesgos cuyo dominio tiene lecciones o patrones.",
          ],
        },
        {
          kind: "note",
          tone: "info",
          text: "Una parte sin datos no penaliza: si el proyecto aún no tiene familias de fallos, «Memoria de defectos» sale como «sin datos» y no cuenta en el índice. El índice mide qué conocimiento hay, no su calidad.",
        },
      ],
    },
    {
      heading: "Cuando alguien rota: el acta de traspaso",
      blocks: [
        {
          kind: "steps",
          items: [
            "Abre [Continuidad](/app/continuity) y elige el proyecto.",
            "Revisa lo que falta: cada parte incompleta enlaza a donde se completa.",
            "Pulsa **Emitir acta de traspaso** (solo administradores de la organización). El acta firma el índice, su desglose y el inventario de ese momento.",
            "Copia el enlace de verificación y compártelo: quien lo abra ve el sello del acta sin necesitar cuenta.",
          ],
        },
        {
          kind: "p",
          text: "Si alguien retoca el contenido del acta, la firma deja de cuadrar y [Verificar acta](/app/verify) lo muestra en rojo.",
        },
      ],
    },
    {
      heading: "Quien llega",
      blocks: [
        {
          kind: "p",
          text: "En el [Onboarding al proyecto](/app/onboarding) pregunta con sus palabras —«¿por qué es inestable el checkout?», «¿a quién pregunto por el sandbox?»— y recibe lo que el equipo dejó escrito, con las fuentes citadas.",
        },
      ],
    },
  ],
};
