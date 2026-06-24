from typing import Any, Callable, Dict, Optional

from src.actions.base import Actuator, CodeHost, NullCodeHost

_CATEGORIES = ("quarantine", "ticket", "self_heal")


class ActionService:
    """Orquesta la capa de acción. Nivel 2: nada externo sin approve. La materialización
    es por-org (codehost_factory) y reintentable (proposed→approved→materialized)."""

    def __init__(self, *, repo, actuators: Dict[str, Actuator],
                 actions_repo=None,
                 codehost_factory: Optional[Callable[[str, str], CodeHost]] = None):
        self.repo = repo                                  # lecturas de contexto (assurance)
        self.actions_repo = actions_repo or repo          # CRUD de acciones
        self.actuators = actuators
        self._codehost_factory = codehost_factory or (lambda org_id, user_id: NullCodeHost())

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
            self.actions_repo.save_actions(user_id=user_id, org_id=org_id,
                                           run_id=run_id, actions=proposals)
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
        action = self.actions_repo.get_action(user_id=user_id, action_id=action_id)
        if action is None or action.get("status") == "rejected":
            return {"approved": False, "materialized": False, "artifact_ref": None}
        if action.get("status") == "materialized":
            return {"approved": True, "materialized": True,
                    "artifact_ref": action.get("artifact_ref")}
        if action.get("status") == "proposed":
            if not self.actions_repo.approve_action(user_id=user_id, action_id=action_id):
                # carrera: alguien más cambió el estado; re-leer
                action = self.actions_repo.get_action(user_id=user_id, action_id=action_id)
                if action is None or action.get("status") not in ("approved", "materialized"):
                    return {"approved": False, "materialized": False, "artifact_ref": None}
                if action.get("status") == "materialized":
                    return {"approved": True, "materialized": True,
                            "artifact_ref": action.get("artifact_ref")}
        # aquí status == 'approved' (recién o de un intento previo)
        if action["kind"] == "self_heal":
            return {"approved": True, "materialized": False, "artifact_ref": None}  # PR = F3c-2
        codehost = self._codehost_factory(action["org_id"], user_id)
        ref = self._materialize(action, codehost)
        self.actions_repo.materialize_action(user_id=user_id, action_id=action_id, artifact_ref=ref)
        return {"approved": True, "materialized": True, "artifact_ref": ref}

    def _materialize(self, action: Dict[str, Any], codehost: CodeHost) -> str:
        payload = action.get("payload") or {}
        marker = f"mnemo:action:{action['id']}"
        if action["kind"] == "ticket":
            return codehost.create_issue(
                title=payload.get("title", ""), body=payload.get("body", ""),
                labels=payload.get("labels", []), marker=marker,
            )
        if action["kind"] == "quarantine":
            dt = payload.get("debt_ticket") or {}
            return codehost.create_issue(
                title=dt.get("title", ""), body=dt.get("body", ""),
                labels=dt.get("labels", []), marker=marker,
            )
        return "stub://unknown"

    def reject_action(self, *, user_id: str, action_id: str, reason: str = "") -> bool:
        return self.actions_repo.reject_action(user_id=user_id, action_id=action_id, reason=reason)
