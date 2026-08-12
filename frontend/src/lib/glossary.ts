export const GLOSSARY: Record<string, string> = {
  foso: "Tus correcciones se acumulan como verdad de referencia: cuantas más, más fino el triaje futuro.",
  briefing: "Resumen ejecutivo del run: veredicto, recomendación y riesgo.",
  gate: "Estado publicado como check de GitHub (listo para merge / bloqueado).",
  "regla_sin_test": "Una regla/flujo/riesgo de QA sin un test que lo cubra.",
  "defecto_sin_conocimiento": "Un defecto recurrente sin una lección capturada.",
  triaje: "Clasificación automática de un fallo (real, flaky, mantenimiento, infra).",
  certificado: "Acta de aseguramiento firmada: prueba verificable del veredicto del run.",
  "risk_score": "Puntuación de riesgo del run, de 0 a 100 (mayor = más atención).",
  calibracion: "Ajuste del motor con tus etiquetas de verdad de referencia.",
  self_heal: "Auto-reparación: PR propuesto que arregla un locator/selector roto.",
  linaje: "Historial de ocurrencias de una familia de defecto a través de proyectos y runs.",
  acciones_nivel2:
    "Acciones que Mnemo propone tras el triaje: cuarentena, ticket o auto-reparación. Ninguna se ejecuta sin tu aprobación.",
  familia_defectos:
    "Mnemo agrupa los fallos con la misma causa aparente en familias y guarda su historial a través de proyectos y runs.",
  precision_motor:
    "Porcentaje de tus correcciones en las que el motor de triaje ya había acertado la categoría. Solo cuenta familias etiquetadas por tu equipo.",
  tipo_conocimiento:
    "Sobre el producto — Lección: algo aprendido de un fallo. Regla de negocio: cómo debe comportarse el sistema. Flujo: un proceso paso a paso. Riesgo: algo que puede salir mal. Glosario: definición de un término. Sobre el oficio del proyecto — Runbook: cómo levantar el entorno o ejecutar algo. Dato de prueba: usuarios, tarjetas o datos con los que se prueba. Contacto: qué equipo o canal lleva cada cosa (roles, no personas). Decisión: qué se acordó y por qué. El tipo decide qué avisos de cobertura puede generar (p. ej. «regla sin test»).",
  confianza:
    "Confirmado: escrito o aprobado por una persona. Inferido: deducido automáticamente del triaje de fallos, aún sin validar.",
};
