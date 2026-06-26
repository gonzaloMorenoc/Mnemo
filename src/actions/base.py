from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class ActionProposal:
    kind: str                       # quarantine | ticket | self_heal
    payload: Dict[str, Any]
    summary: str


class Actuator(Protocol):
    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]: ...


class CodeHost(Protocol):
    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str: ...
    def open_draft_pr(self, *, title: str, body: str, file_path: str,
                      old_str: str, new_str: str, marker: str = "") -> Optional[str]: ...
    def read_file(self, file_path: str) -> Optional[str]: ...


class NullCodeHost:
    """Stub: NO escribe en ningún sitio externo (default de tests / sin GitHub)."""

    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str:
        return "stub://issue/pending"

    def open_draft_pr(self, *, title: str, body: str, file_path: str,
                      old_str: str, new_str: str, marker: str = "") -> Optional[str]:
        return "stub://pr/pending"

    def read_file(self, file_path: str) -> Optional[str]:
        return None
