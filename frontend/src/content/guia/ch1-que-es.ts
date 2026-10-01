import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "que-es-mnemo",
  title: "Qué es Mnemo",
  summary: "El problema que resuelve y qué lo hace distinto.",
  sections: [
    {
      blocks: [
        {
          kind: "p",
          text: "En una consultora de QA, las personas rotan entre proyectos y clientes. Cuando quien lleva un proyecto se va, con ella se van cosas que no están escritas en ningún sitio: cómo se levanta el entorno, con qué datos se prueba, a quién se pregunta cuando algo se cae y por qué un test que parece inestable en realidad no lo es.",
        },
        {
          kind: "p",
          text: "Mnemo es la memoria del proyecto que se queda. Se alimenta del trabajo de cada día —los runs del CI y lo que el equipo escribe al etiquetar un fallo—, mide cuánto sabe de cada proyecto y lo devuelve a quien llega, con la fuente citada.",
        },
      ],
    },
    {
      heading: "Lo que lo hace distinto",
      blocks: [
        {
          kind: "list",
          items: [
            "**Sabe qué falló ayer.** Una wiki no; Mnemo une cada run con sus familias de defectos, la razón con la que se etiquetaron y las lecciones aprendidas.",
            "**Mide la continuidad.** Un índice por proyecto dice cuánto de él está en Mnemo, con su desglose. Lo ves en [Continuidad](/app/continuity).",
            "**Firma el traspaso.** Cuando alguien rota, el acta de traspaso deja constancia de lo que quedó depositado, y cualquiera la comprueba en [Verificar acta](/app/verify) sin cuenta.",
          ],
        },
        {
          kind: "note",
          tone: "info",
          text: "Esta Guía explica cómo funciona Mnemo. No la confundas con el [Onboarding al proyecto](/app/onboarding): ahí preguntas por el proyecto concreto de tu cliente.",
        },
      ],
    },
  ],
};
