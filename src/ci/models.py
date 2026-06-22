from typing import List, Literal, Optional

from pydantic import BaseModel


class CiTestResult(BaseModel):
    test_name: str
    status: Literal["pass", "fail", "flaky", "skipped"]
    retried: bool = False
    error_type: Optional[str] = None
    message: Optional[str] = None
    trace: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    dom: Optional[str] = None


class CiRunArtifact(BaseModel):
    project: str
    org_id: str
    commit_sha: str
    source: str = "playwright"
    tests: List[CiTestResult]
