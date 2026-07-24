import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "preguntas-frecuentes",
  title: "Preguntas frecuentes",
  summary: "Las dudas más comunes, respondidas.",
  sections: [
    {
      blocks: [
        {
          kind: "p",
          text: "**¿Por qué mi acta dice «Sin confirmar»?** Porque el reporte no probó que corriera una batería real de tests: llegó vacío, o sin un manifiesto completo. No es un fallo, es honestidad. Un run con fallos, en cambio, sigue siendo rojo.",
        },
        {
          kind: "p",
          text: "**¿Mis datos salen de mi organización?** No. La memoria, los runs y las actas viven dentro de tu organización y no se mezclan con los de nadie más.",
        },
        {
          kind: "p",
          text: "**¿Qué es un gate?** El [[gate]] es el estado que Mnemo publica como check de GitHub en tu PR: listo para merge o bloqueado.",
        },
        {
          kind: "p",
          text: "**¿En qué se diferencian Assurance y Autopilot?** [Assurance](/app/assurance) te da el veredicto y el [[briefing]] de un run de un vistazo; [Autopilot](/app/autopilot) es donde bajas al detalle: revisas el triaje, apruebas acciones y emites el acta.",
        },
      ],
    },
  ],
};
