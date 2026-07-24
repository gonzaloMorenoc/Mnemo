import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "la-memoria-de-qa",
  title: "La memoria de QA",
  summary: "Capturar, preguntar y reutilizar lo aprendido.",
  sections: [
    {
      heading: "Capturar y preguntar",
      blocks: [
        {
          kind: "p",
          text: "La memoria es donde tu equipo guarda lo que sabe: reglas de negocio, flujos, riesgos y lecciones de fallos pasados. Se captura en [Conocimiento](/app/knowledge). Y cuando alguien pregunta «¿cómo gestionamos los errores de pago?», Mnemo responde usando solo esa memoria y citando de dónde sale cada dato. Si no lo sabe, te lo dice en vez de inventárselo.",
        },
      ],
    },
    {
      heading: "La IA propone, tú apruebas",
      blocks: [
        {
          kind: "p",
          text: "Parte del conocimiento entra solo: Mnemo genera propuestas a partir del triaje, y también puedes importar desde Jira o Confluence. Nada de eso se da por bueno automáticamente. Todo cae en una bandeja de propuestas dentro de [Conocimiento](/app/knowledge), y tú decides qué entra en la memoria y qué no.",
        },
      ],
    },
    {
      heading: "Para qué sirve la memoria",
      blocks: [
        {
          kind: "p",
          text: "Lo que guardas no se queda quieto. Alimenta el [Plan de pruebas](/app/test-plan), acelera el [Onboarding al proyecto](/app/onboarding) de quien llega nuevo, y aflora los huecos de cobertura en el [Grafo de conocimiento](/app/graph).",
        },
      ],
    },
  ],
};
