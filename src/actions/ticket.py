from typing import Any, Dict

from src.actions.base import ActionProposal


class TicketActuator:
    """Defecto real → ticket enriquecido: root-cause (RootCauseAnalyzer, inyectado) +
    linaje cross-proyecto. Prefiere el root_cause ya guardado; degrada a
    'no disponible' si el LLM falla (nunca rompe)."""

    def __init__(self, analyzer: Any):
        self._analyzer = analyzer

    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> ActionProposal:
        ev = verdict.get("evidence_bundle") or {}
        test_name = context.get("test_name") or "(test desconocido)"
        lineage = ev.get("lineage_projects") or []
        rule_applied = ev.get("rule_applied") or "desconocida"
        family = context.get("family") or {}
        failures = context.get("failures") or []

        root_cause = family.get("root_cause")
        if not root_cause and failures:
            try:
                root_cause = self._analyzer.analyze(family, failures, lineage=lineage)
            except TypeError:
                # analyzer sin soporte de lineage (compat) → llamada antigua
                root_cause = self._analyzer.analyze(family, failures)
            except Exception:  # noqa: BLE001 — degrada; el ticket se propone igual
                root_cause = None

        lineage_line = (
            f"Esta familia ya apareció en: {', '.join(lineage)}." if lineage
            else "Primera aparición de esta familia."
        )
        body = (
            f"**Defecto real** en `{test_name}` "
            f"(confianza {verdict.get('confidence')}, regla {rule_applied}).\n\n"
            f"{lineage_line}\n\n"
            "## Causa raíz (hipótesis)\n"
            f"{root_cause or '_root-cause no disponible (LLM no accesible)._'}\n"
        )
        return ActionProposal(
            kind="ticket",
            payload={"title": f"[Defecto] {test_name}", "body": body, "labels": ["bug", "mnemo"]},
            summary=f"Ticket de defecto real: {test_name}",
        )
