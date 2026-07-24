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
          text: "Un equipo de QA que salta de cliente en cliente pierde contexto en cada salto. El triaje que hiciste el mes pasado se vuelve a hacer, la lección que aprendió un compañero se queda en su cabeza, y cuando llega el día de liberar cuesta demostrar por qué la calidad de esa release es la que dices que es.",
        },
        {
          kind: "p",
          text: "Mnemo ataca esas tres cosas. Recuerda lo que tu equipo aprende, te ayuda a clasificar los fallos de cada ejecución, y firma un veredicto que cualquiera puede comprobar.",
        },
      ],
    },
    {
      heading: "Lo que lo hace distinto",
      blocks: [
        {
          kind: "p",
          text: "El diferenciador es el [[certificado]]: un acta firmada del veredicto de un run. No es un PDF bonito, es una prueba criptográfica. Quien la reciba puede comprobarla en [Verificar acta](/app/verify) sin tener cuenta en Mnemo, y sabrá que nadie la ha tocado desde que se emitió.",
        },
        {
          kind: "note",
          tone: "info",
          text: "Esta Guía explica cómo funciona Mnemo. No la confundas con el [Onboarding al proyecto](/app/onboarding), que es otra cosa: ahí Mnemo aprende el proyecto concreto de tu cliente para ponerte al día.",
        },
      ],
    },
  ],
};
