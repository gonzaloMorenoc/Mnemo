from typing import Any, Dict, Optional

from src.actions.base import Actuator, CodeHost, NullCodeHost

_CATEGORIES = ("quarantine", "ticket", "self_heal")


class ActionService:
    """Orquesta la capa de acción: de los veredictos resueltos genera acciones propuestas,
    y materializa/rechaza al aprobar. Nivel 2: nada externo sin approve."""

    def __init__(
        self, *, repo, actuators: Dict[str, Actuator], codehost: Optional[CodeHost] = None
    ):
        self.repo = repo
        self.actuators = actuators
        self.codehost = codehost or NullCodeHost()

    def propose_actions(self, *, user_id: str, run_id: str) -> Dict[str, int]:
        verdicts = self.repo.get_run_actionable_verdicts(user_id=user_id, run_id=run_id)
        counts = {c: 0 for c in _CATEGORIES}
        counts["skipped"] = 0
        proposals = []
        org_id = None
        for v in verdicts:
            org_id = v.get("org_id") or org_id
            actuator = self.actuators.get(v["category"])
            if actuator is None:
                counts["skipped"] += 1
                continue
            proposal = actuator.propose(v, self._context_for(user_id, v))
            if proposal is None:
                counts["skipped"] += 1
                continue
            proposals.append({
                "triage_verdict_id": v["verdict_id"], "kind": proposal.kind,
                "payload": proposal.payload, "summary": proposal.summary,
            })
            counts[proposal.kind] = counts.get(proposal.kind, 0) + 1
        if proposals and org_id:
            self.repo.save_actions(user_id=user_id, org_id=org_id, run_id=run_id, actions=proposals)
        return counts

    def _context_for(self, user_id: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"test_name": verdict.get("test_name")}
        category = verdict["category"]
        if category == "real" and verdict.get("defect_family_id"):
            fam = self.repo.get_family_with_failures(
                user_id=user_id, defect_id=verdict["defect_family_id"]
            )
            if fam:
                ctx["family"] = fam.get("family") or {}
                ctx["failures"] = fam.get("failures") or []
        elif category == "maintenance" and verdict.get("failure_id"):
            sh = self.repo.get_selfheal_context(user_id=user_id, failure_id=verdict["failure_id"])
            if sh:
                ctx.update(sh)
        return ctx

    def approve_action(self, *, user_id: str, action_id: str) -> Dict[str, Any]:
        action = self.repo.get_action(user_id=user_id, action_id=action_id)
        if action is None or action.get("status") != "proposed":
            return {"approved": False, "artifact_ref": None}
        ref = self._materialize(action)
        ok = self.repo.approve_action(user_id=user_id, action_id=action_id, artifact_ref=ref)
        return {"approved": ok, "artifact_ref": ref}

    def _materialize(self, action: Dict[str, Any]) -> str:
        payload = action.get("payload") or {}
        if action["kind"] == "ticket":
            return self.codehost.create_issue(
                title=payload.get("title", ""), body=payload.get("body", ""),
                labels=payload.get("labels", []),
            )
        if action["kind"] == "quarantine":
            dt = payload.get("debt_ticket") or {}
            return self.codehost.create_issue(
                title=dt.get("title", ""), body=dt.get("body", ""), labels=dt.get("labels", []),
            )
        return "stub://unknown"

    def reject_action(self, *, user_id: str, action_id: str, reason: str = "") -> bool:
        return self.repo.reject_action(user_id=user_id, action_id=action_id, reason=reason)
