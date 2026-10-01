from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class CiTestResult(BaseModel):
    test_name: str = Field(max_length=2000)
    status: Literal["pass", "fail", "flaky", "skipped"]
    retried: bool = False
    error_type: Optional[str] = Field(default=None, max_length=500)
    message: Optional[str] = Field(default=None, max_length=100_000)
    trace: Optional[str] = Field(default=None, max_length=200_000)
    file: Optional[str] = Field(default=None, max_length=2000)
    line: Optional[int] = None
    dom: Optional[str] = Field(default=None, max_length=5_000_000)


class CiRunArtifact(BaseModel):
    project: str = Field(max_length=500)
    org_id: str = Field(max_length=200)
    commit_sha: str = Field(max_length=200)
    # Los formatos que admite el CHECK de test_runs.source (migración 005): fuera de
    # esta lista, el INSERT moría con un 500 en vez de devolver un 422 al CI.
    source: Literal["allure", "junit", "testng", "cucumber",
                    "playwright", "cypress", "robot"] = "playwright"
    run_uid: Optional[str] = Field(default=None, max_length=200)
    tests: List[CiTestResult] = Field(max_length=10_000)
