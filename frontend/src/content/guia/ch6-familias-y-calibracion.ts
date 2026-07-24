import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "familias-y-calibracion",
  title: "Familias de defectos y calibración",
  summary: "Cómo se agrupan los fallos y cómo afinas el motor.",
  sections: [
    {
      heading: "Familias",
      blocks: [
        {
          kind: "p",
          text: "Cuando el mismo fallo aparece una y otra vez, no quieres verlo como diez incidencias sueltas. Mnemo agrupa los fallos con la misma causa aparente en [[familia_defectos]] y guarda su [[linaje]]: dónde ha aparecido antes, en qué proyectos y en qué runs. Las exploras en [Defect DNA](/app/defects).",
        },
      ],
    },
    {
      heading: "Calibrar el motor",
      blocks: [
        {
          kind: "p",
          text: "Aquí es donde Mnemo se vuelve tuyo. Cuando etiquetas una familia con tu verdad de referencia —esto era flaky, esto era real—, estás haciendo [[calibracion]]. Cada etiqueta afina el triaje del futuro. Ese poso de correcciones es el [[foso]]: cuanto más grande, más difícil de replicar por cualquier otro.",
        },
      ],
    },
    {
      heading: "Qué mide la precisión",
      blocks: [
        {
          kind: "p",
          text: "La [[precision_motor]] te dice qué porcentaje de tus correcciones el motor ya había acertado por su cuenta. Solo cuenta las familias que tu equipo ha etiquetado, así que es una medida honesta de cómo de bien te entiende. La sigues en [Calibración](/app/calibration).",
        },
      ],
    },
  ],
};
