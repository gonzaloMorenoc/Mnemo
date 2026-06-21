"""
TDD tests for four confirmed Jira connector bugs:
  A – fingerprint collapses distinct Jira keys
  B – UTF-8 BOM in CSV export raises ValueError
  C – pagination stops after page 1 when total=None
  D – InvalidToken from decrypt_token escapes as 500 instead of 400
"""
import pytest

from src.ingest.models import FailureRecord
from src.defects.fingerprint import fingerprint
from src.jira.export import parse_jira_export
from src.jira.client import JiraApiClient


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _jira_rec(key: str, msg: str) -> FailureRecord:
    return FailureRecord(
        test_name=key,
        error_type="Bug",
        message=msg,
        trace=None,
        project="p",
        source="jira",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug A – fingerprint must be unique per Jira key
# ──────────────────────────────────────────────────────────────────────────────

def test_jira_distinct_keys_distinct_fingerprints():
    """Two Jira bugs with nearly identical text but different keys must NOT collide."""
    fp1 = fingerprint(_jira_rec("PROJ-1", "Login fails on page 1"))
    fp2 = fingerprint(_jira_rec("PROJ-2", "Login fails on page 2"))
    assert fp1 != fp2, (
        "fingerprint collapsed PROJ-1 and PROJ-2 — the issue key must be included "
        "in the basis when source='jira'"
    )


def test_jira_same_key_same_fingerprint():
    """Identical Jira bug must produce the same fingerprint (idempotent)."""
    r = _jira_rec("PROJ-42", "Checkout button unresponsive")
    assert fingerprint(r) == fingerprint(r)


# ──────────────────────────────────────────────────────────────────────────────
# Non-regression: non-jira fingerprint MUST be byte-identical to the old logic
# ──────────────────────────────────────────────────────────────────────────────

def test_non_jira_fingerprint_unchanged():
    """Non-Jira records whose normalised messages are equal must still match."""
    r1 = FailureRecord(
        test_name="t1", error_type="TimeoutException",
        message="timeout after 100ms", trace="at A.java:1",
        project="p", source="junit",
    )
    r2 = FailureRecord(
        test_name="t2", error_type="TimeoutException",
        message="timeout after 999ms", trace="at A.java:2",
        project="p", source="junit",
    )
    # Both traces normalise to the same top_frame; digits are stripped from msgs
    assert fingerprint(r1) == fingerprint(r2), (
        "non-jira fingerprint behaviour changed — must be byte-identical to old logic"
    )


def test_non_jira_different_errors_differ():
    """Non-Jira fingerprint still differentiates genuinely distinct errors."""
    r1 = FailureRecord(
        test_name="t1", error_type="TimeoutException",
        message="timeout waiting for element", trace="at A.java:1",
        project="p", source="allure",
    )
    r2 = FailureRecord(
        test_name="t2", error_type="NullPointerException",
        message="null pointer on submit", trace="at B.java:1",
        project="p", source="allure",
    )
    assert fingerprint(r1) != fingerprint(r2)


# ──────────────────────────────────────────────────────────────────────────────
# Bug B – UTF-8 BOM in CSV export
# ──────────────────────────────────────────────────────────────────────────────

def test_csv_with_bom_parses():
    """A CSV byte-string with a leading UTF-8 BOM (EF BB BF) must parse cleanly."""
    # Encode with BOM prefix explicitly — simulates a Windows Jira CSV export
    content = (
        "﻿Issue key,Summary,Description,Issue Type,Status\r\n"
        "P-1,Checkout fails,boom,Bug,Open\r\n"
    ).encode("utf-8")
    bugs = parse_jira_export(content)
    assert len(bugs) == 1
    assert bugs[0].key == "P-1"
    assert bugs[0].summary == "Checkout fails"


def test_csv_without_bom_still_parses():
    """Existing CSV without BOM must continue to work (regression guard)."""
    content = (
        "Issue key,Summary,Description,Issue Type,Status\r\n"
        "P-2,Login broken,,Bug,Open\r\n"
    ).encode("utf-8")
    bugs = parse_jira_export(content)
    assert len(bugs) == 1
    assert bugs[0].key == "P-2"


# ──────────────────────────────────────────────────────────────────────────────
# Bug C – pagination must not stop early when total=None
# ──────────────────────────────────────────────────────────────────────────────

class _FakeJiraTotalNone:
    """Fake Jira API that never returns 'total' (some on-prem instances omit it)."""

    url = "https://acme.atlassian.net"

    def __init__(self):
        self.calls = 0

    def jql(self, jql, start=0, limit=50, fields=None):
        self.calls += 1
        if start == 0:
            return {
                "total": None,
                "issues": [
                    {
                        "key": "B-1",
                        "fields": {
                            "summary": "s",
                            "description": "d",
                            "issuetype": {"name": "Bug"},
                            "status": {"name": "Open"},
                        },
                    }
                ],
            }
        # Second page is empty → the empty-page guard must terminate the loop
        return {"total": None, "issues": []}


def test_pagination_total_none_does_not_truncate():
    """When total=None the client must continue fetching until an empty page."""
    c = JiraApiClient.__new__(JiraApiClient)
    c._jira = _FakeJiraTotalNone()
    bugs = c.fetch_bugs("issuetype = Bug", page_size=1)
    assert len(bugs) == 1, "must return the one available bug"
    # 2 calls: page with 1 issue, then empty page that terminates loop
    assert c._jira.calls == 2, (
        f"expected 2 API calls (page+empty), got {c._jira.calls}; "
        "total=None must not short-circuit after first page"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug D – InvalidToken / RuntimeError from decrypt_token must surface as ValueError
# ──────────────────────────────────────────────────────────────────────────────

def test_decrypt_invalid_token_raises_valueerror(monkeypatch):
    """InvalidToken from cryptography.fernet must be caught and re-raised as ValueError."""
    from cryptography.fernet import InvalidToken
    from src.jira import integrations_repository as ir

    # Patch decrypt_token to simulate key-rotation / ciphertext corruption
    monkeypatch.setattr(ir, "decrypt_token", lambda enc: (_ for _ in ()).throw(InvalidToken()))

    repo = ir.IntegrationsRepository.__new__(ir.IntegrationsRepository)
    with pytest.raises(ValueError, match="reconfigura"):
        repo._decrypt("corrupted-ciphertext")


def test_decrypt_runtime_error_raises_valueerror(monkeypatch):
    """RuntimeError (missing MNEMO_SECRET_KEY) must also surface as ValueError."""
    from src.jira import integrations_repository as ir

    monkeypatch.setattr(ir, "decrypt_token", lambda enc: (_ for _ in ()).throw(RuntimeError("no key")))

    repo = ir.IntegrationsRepository.__new__(ir.IntegrationsRepository)
    with pytest.raises(ValueError, match="reconfigura"):
        repo._decrypt("anything")
