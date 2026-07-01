export const GLOSSARY: Record<string, string> = {
  foso: "El foso: tus correcciones acumuladas que calibran el motor de triaje.",
  briefing: "Resumen ejecutivo del run: veredicto, recomendación y riesgo.",
  gate: "Estado publicado como check de GitHub (listo para merge / bloqueado).",
  "regla_sin_test": "Una regla/flujo/riesgo de QA sin un test que lo cubra.",
  "defecto_sin_conocimiento": "Un defecto recurrente sin una lección capturada.",
  triaje: "Clasificación automática de un fallo (real, flaky, mantenimiento, infra).",
  certificado: "Certificado de aseguramiento firmado: prueba verificable del run.",
  "risk_score": "Puntuación de riesgo del run (mayor = más atención).",
  calibracion: "Ajuste del motor con tus etiquetas de verdad de referencia.",
  self_heal: "Auto-reparación: PR propuesto que arregla un locator/selector roto.",
  linaje: "Historial de ocurrencias de una familia de defecto a través de proyectos y runs.",
};
