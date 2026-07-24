import type { Chapter } from "./types";

export const chapter: Chapter = {
  slug: "el-acta-firmada",
  title: "El acta firmada",
  summary: "Qué garantiza y cómo comprobarla.",
  sections: [
    {
      heading: "Qué garantiza",
      blocks: [
        {
          kind: "p",
          text: "El acta lleva una firma criptográfica. Esa firma prueba dos cosas: que el contenido no se ha alterado desde que se emitió, y que lo emitió esta instancia de Mnemo y no otra. Quien reciba el acta la comprueba en [Verificar acta](/app/verify) pegando el JSON, sin necesidad de cuenta. La verificación es matemática pura.",
        },
      ],
    },
    {
      heading: "El manifiesto de ejecución",
      blocks: [
        {
          kind: "p",
          text: "El acta no registra solo los fallos: también guarda qué se ejecutó de verdad —cuántos tests corrieron, cuántos pasaron, cuántos fallaron y cuántos se omitieron—. Ese manifiesto es lo que impide firmar «apto» un run del que ni siquiera puedes probar que corrió una batería real.",
        },
      ],
    },
    {
      heading: "Los cuatro veredictos",
      blocks: [
        {
          kind: "list",
          items: [
            "**Apto**: run limpio, con una ejecución completa que lo respalda.",
            "**Apto con reservas**: hay defectos reales recurrentes o mantenimiento; se puede liberar, pero mirándolo.",
            "**No apto**: hay un defecto real sin precedente o ítems pendientes de tu aprobación.",
            "**Sin confirmar**: no se pudo probar que corriera una batería real —por ejemplo, un reporte vacío o sin un manifiesto completo—.",
          ],
        },
        {
          kind: "note",
          tone: "warn",
          text: "Un run con fallos nunca se esconde detrás de «Sin confirmar»: sigue siendo rojo. «Sin confirmar» es honestidad sobre lo que Mnemo no puede demostrar, no una excusa.",
        },
      ],
    },
  ],
};
