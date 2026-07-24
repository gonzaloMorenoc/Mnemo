import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "analizar-un-run",
  title: "Analizar un run",
  summary: "El flujo central, paso a paso.",
  sections: [
    {
      blocks: [
        {
          kind: "p",
          text: "Un run es una ejecución de tus tests. Cuando entra en Mnemo, no se queda en «pasaron 120, fallaron 5»: pasa por tres fases que convierten esos números en una decisión que puedes defender.",
        },
        {
          kind: "steps",
          items: [
            "El [[triaje]] clasifica cada fallo: real, flaky, de mantenimiento o de infraestructura. Así distingues lo que importa del ruido.",
            "Mnemo propone [[acciones_nivel2]] para lo que encontró: poner un test en cuarentena, abrir un ticket o intentar una [[self_heal]]. Ninguna se ejecuta sin que tú la apruebes.",
            "Emite el [[certificado]] con el veredicto, y el [[gate]] publica ese resultado como un check en tu PR de GitHub.",
          ],
        },
        {
          kind: "note",
          tone: "info",
          text: "Todo esto ocurre en [Autopilot](/app/autopilot): ahí revisas el triaje, apruebas o rechazas cada acción y generas el acta.",
        },
      ],
    },
  ],
};
