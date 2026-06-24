from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ActionProposal:
    kind: str                       # quarantine | ticket | self_heal
    payload: Dict[str, Any]
    summary: str


class Actuator(Protocol):
    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]: ...


class CodeHost(Protocol):
    def create_issue(self, *, title: str, body: str, labels: List[str]) -> str: ...
    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str: ...


class NullCodeHost:
    """Stub: NO escribe en ningún sitio externo; devuelve un ref placeholder.
    El CodeHost real (GitHub App) es F3c."""

    def create_issue(self, *, title: str, body: str, labels: List[str]) -> str:
        return "stub://issue/pending"

    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str:
        return "stub://pr/pending"
