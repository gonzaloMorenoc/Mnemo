from typing import Any, Dict, Optional

from src.actions.base import ActionProposal


class QuarantineActuator:
    """Flaky → cuarentena con deuda. Determinista (sin LLM). SIEMPRE ticket de deuda
    (cuarentena sin ticket = ocultar bugs)."""

    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]:
        test_name = context.get("test_name") or "(test desconocido)"
        ev = verdict.get("evidence_bundle") or {}
        family_id = ev.get("family_id")
        debt_ticket = {
            "title": f"[Flaky] {test_name}",
            "body": (
                f"El test `{test_name}` se clasificó como **flaky** "
                f"(confianza {verdict.get('confidence')}).\n\n"
                f"Familia de defecto: `{family_id}`.\n\n"
                "Puesto en cuarentena con **deuda abierta**: no se oculta el fallo, queda "
                "registrado para revisión. Quitar de cuarentena cuando el test se estabilice."
            ),
            "labels": ["flaky", "mnemo-debt"],
        }
        annotation = {
            "test_name": test_name,
            "suggestion": (
                f"Anotar `{test_name}` con `test.fixme()` o tag `@flaky` y un retry; "
                "mantener la deuda abierta hasta estabilizar."
            ),
        }
        return ActionProposal(
            kind="quarantine",
            payload={"debt_ticket": debt_ticket, "annotation": annotation},
            summary=f"Cuarentena + deuda: {test_name}",
        )
