import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "primeros-pasos",
  title: "Primeros pasos",
  summary: "De cero a tu primer veredicto.",
  sections: [
    {
      heading: "Tu organización",
      blocks: [
        {
          kind: "p",
          text: "Todo en Mnemo vive dentro de una organización: la memoria, los runs y las actas. Lo primero es crear la tuya o unirte a una que ya exista, desde [Organización](/app/org). Nada de lo que subes se mezcla con el de otra organización.",
        },
      ],
    },
    {
      heading: "Conecta tu CI o sube un reporte",
      blocks: [
        {
          kind: "p",
          text: "Hay dos maneras de meter un run en Mnemo. La rápida para probar es subir un reporte a mano; la que usarás cada día es dejar que tu pipeline lo mande solo.",
        },
        {
          kind: "steps",
          items: [
            "Genera un token de ingesta en [Integraciones](/app/integrations) y apúntalo desde tu pipeline de CI. A partir de ahí, cada ejecución llega sola.",
            "O, si solo quieres probar, sube a mano el reporte de tu última ejecución (`junit.xml`, Playwright, Cypress y unos cuantos formatos más) en [Autopilot](/app/autopilot).",
          ],
        },
      ],
    },
    {
      heading: "Tu primer veredicto",
      blocks: [
        {
          kind: "p",
          text: "En cuanto llega el reporte, Mnemo hace el [[triaje]] de los fallos y calcula un veredicto para el run. Lo ves en [Autopilot](/app/autopilot). Ese veredicto es el punto de partida del resto de la Guía.",
        },
      ],
    },
  ],
};
