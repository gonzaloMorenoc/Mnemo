from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.actions.base import ActionProposal
from src.actions.selfheal.candidates import find_candidates, rank
from src.actions.selfheal.dom import find_element, signature
from src.actions.selfheal.selector import BrokenSelector, parse_broken_selector

_TOP_N = 3


def _broken_str(b: BrokenSelector) -> str:
    if b.kind == "role":
        if b.name:
            return f"getByRole('{b.value}', {{ name: '{b.name}' }})"
        return f"getByRole('{b.value}')"
    if b.kind == "testid":
        return f"getByTestId('{b.value}')"
    if b.kind == "text":
        return f"getByText('{b.value}')"
    return f"locator('{b.value}')"


class SelfHealActuator:
    """maintenance → locator robusto (determinista). El explainer (LLM) es opcional y
    degradable. Devuelve None (→ skipped) si no puede curar; NUNCA lanza."""

    def __init__(self, explainer: Optional[Any] = None):
        self._explainer = explainer

    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]:
        try:
            broken = parse_broken_selector(context.get("error_message") or "", context.get("trace"))
            green, failure = context.get("green_dom"), context.get("failure_dom")
            if broken is None or not green or not failure:
                return None
            old_el = find_element(BeautifulSoup(green, "html.parser"), broken)
            if old_el is None:
                return None
            sig = signature(old_el)
            ranked = rank(find_candidates(BeautifulSoup(failure, "html.parser"), sig), sig)
            if not ranked:
                return None
            top = ranked[0]
            broken_str = _broken_str(broken)
            cands = [{"locator": c.locator, "score": c.score, "why": c.why} for c in ranked[:_TOP_N]]
            reasoning = self._reasoning(broken_str, top.locator, cands)
            return ActionProposal(
                kind="self_heal",
                payload={"broken_locator": broken_str, "suggested_locator": top.locator,
                         "candidates": cands, "reasoning": reasoning},
                summary=f"Self-heal: {broken_str} → {top.locator}",
            )
        except Exception:  # noqa: BLE001 — el self-heal nunca rompe propose_actions
            return None

    def _reasoning(self, broken_str: str, suggested: str, candidates) -> str:
        template = (
            f"El locator `{broken_str}` dejó de resolver tras el cambio de DOM; `{suggested}` "
            "apunta al mismo elemento por semántica estable (role/nombre/testid), más robusto."
        )
        if self._explainer is None:
            return template
        try:
            return self._explainer.explain(
                broken_locator=broken_str, suggested_locator=suggested, candidates=candidates
            )
        except Exception:  # noqa: BLE001 — LLM degrada a plantilla
            return template
