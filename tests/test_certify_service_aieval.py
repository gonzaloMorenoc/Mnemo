"""Unit tests for CertificateService.generate — ai_eval integration paths.

Tests added to cover the two gaps flagged in PR-B1 Task 3 review:
1. Service-level graceful degradation: compute_ai_eval raises → ai_eval=None, cert still issues.
2. Provider present and scores: ai_eval is included in self_eval with method=="llm_judge".
"""
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.certify.service import CertificateService


# ---------------------------------------------------------------------------
# Helper: Ed25519 keypair (same pattern as tests/test_certificate.py)
# ---------------------------------------------------------------------------

def _keys():
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = sk.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pub


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_VERDICTS = [
    {
        "failure_id": "f1",
        "category": "real",
        "rule_applied": "R6_ambiguous",
        "requires_approval": True,
        "llm_assisted": True,
        "evidence_bundle": {"sig": "x"},
    }
]

_META = {"org_id": "o", "project": "p", "commit_sha": "s",
         "manifest": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "complete": True}}
_CREATED_AT = "2026-06-26T00:00:00Z"


def _make_service(priv, pub, *, llm_provider=None):
    """Build a CertificateService with fully-mocked repos."""
    repo = MagicMock()
    repo.get_triage_for_run.return_value = _VERDICTS
    repo.get_calibration_metrics.return_value = {}

    cert_repo = MagicMock()
    cert_repo.get_run_meta.return_value = _META
    cert_repo.save_certificate.return_value = None

    return CertificateService(
        repo=repo,
        cert_repo=cert_repo,
        private_key=priv,
        public_key=pub,
        mnemo_version="1.0",
        model_version="test-model",
        llm_provider=llm_provider,
    )


# ---------------------------------------------------------------------------
# Test 1 — provider available and scores → ai_eval present in self_eval
# ---------------------------------------------------------------------------

def test_generate_includes_ai_eval_when_provider_scores():
    priv, pub = _keys()

    # Minimal LLM provider stub: .complete() returns valid JSON scores
    provider = MagicMock()
    provider.complete.return_value = '{"faithfulness":0.9,"groundedness":0.9}'

    svc = _make_service(priv, pub, llm_provider=provider)
    result = svc.generate(user_id="u1", run_id="r1", created_at=_CREATED_AT)

    ai_eval = result["canonical_json"]["self_eval"]["ai_eval"]
    assert ai_eval is not None, "ai_eval should be present when provider scores"
    assert ai_eval["method"] == "llm_judge"
    assert ai_eval["n"] == 1


# ---------------------------------------------------------------------------
# Test 2 — compute_ai_eval raises → cert still issues with ai_eval=None
# ---------------------------------------------------------------------------

def test_generate_degrades_to_none_when_judge_raises(monkeypatch):
    priv, pub = _keys()

    # Patch compute_ai_eval at the location imported by the service module
    monkeypatch.setattr(
        "src.certify.service.compute_ai_eval",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("LLM unavailable")),
    )

    svc = _make_service(priv, pub, llm_provider=None)

    # Must NOT raise — graceful degradation
    result = svc.generate(user_id="u1", run_id="r1", created_at=_CREATED_AT)

    assert result["canonical_json"]["self_eval"]["ai_eval"] is None, (
        "ai_eval should be None when compute_ai_eval raises"
    )


# ---------------------------------------------------------------------------
# D2 — certificar un release VERDE (0 fallos, 0 veredictos) vs. uno SIN TRIAR
# ---------------------------------------------------------------------------

def _make_service_greenish(priv, pub, *, verdicts, n_failures, calibration=None):
    repo = MagicMock()
    repo.get_triage_for_run.return_value = verdicts
    repo.count_failures_for_run.return_value = n_failures
    repo.get_calibration_metrics.return_value = calibration or {}
    cert_repo = MagicMock()
    cert_repo.get_run_meta.return_value = _META
    cert_repo.save_certificate.return_value = None
    return CertificateService(repo=repo, cert_repo=cert_repo, private_key=priv, public_key=pub,
                              mnemo_version="1.0", model_version="test-model")


def test_generate_green_run_certifies_apto():
    priv, pub = _keys()
    cal = {"accuracy": 0.85, "total": 150, "por_categoria": {}}
    svc = _make_service_greenish(priv, pub, verdicts=[], n_failures=0, calibration=cal)
    result = svc.generate(user_id="u1", run_id="r1", created_at=_CREATED_AT)
    assert result["verdict"] == "apto"
    assert result["risk_score"] == 0
    assert result["canonical_json"]["evidence"] == []


def test_generate_untriaged_run_raises():
    priv, pub = _keys()
    svc = _make_service_greenish(priv, pub, verdicts=[], n_failures=5)
    with pytest.raises(ValueError):
        svc.generate(user_id="u1", run_id="r1", created_at=_CREATED_AT)
