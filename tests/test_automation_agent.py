"""Tests for src.automation.agent.generate_playwright_test (TDD)."""
from unittest.mock import patch

import pytest

from src.automation.agent import generate_playwright_test

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

_CASE_GHERKIN = {
    "title": "Login exitoso",
    "gherkin": "Feature: Login\n  Scenario: Happy path\n    Given the login page\n    When user submits valid credentials\n    Then dashboard is visible",
}

_CASE_STEPS = {
    "title": "Add to cart",
    "steps": ["Navigate to product page", "Click Add to Cart", "Verify cart count is 1"],
}

_LLM_RESPONSE = {
    "code": "import { test, expect } from '@playwright/test';\ntest('login', async ({ page }) => { await page.goto('/login'); });",
    "filename": "login.spec.ts",
    "notes": "Verify selectors before running.",
}

# ---------------------------------------------------------------------------
# Happy-path: LLM returns a valid response
# ---------------------------------------------------------------------------

def test_returns_llm_code_and_filename_when_llm_succeeds():
    """generate_structured returns a valid dict → result carries that code/filename."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE):
        result = generate_playwright_test(case=_CASE_GHERKIN)

    assert result["code"] == _LLM_RESPONSE["code"]
    assert result["filename"] == "login.spec.ts"
    assert result["notes"] == _LLM_RESPONSE["notes"]


def test_style_sample_included_in_context_when_given():
    """style_sample is appended to context with id='style_sample' when provided."""
    style = "import { test } from '@playwright/test'; // existing style"
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_GHERKIN, style_sample=style)

    call_kwargs = mock_gs.call_args.kwargs
    context_ids = [c["id"] for c in call_kwargs["context"]]
    assert "style_sample" in context_ids
    # The style_sample content must be in the context entry
    style_ctx = next(c for c in call_kwargs["context"] if c["id"] == "style_sample")
    assert style in style_ctx["content"]


def test_style_sample_absent_from_context_when_not_given():
    """When style_sample is None, context does NOT include a style_sample entry."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_GHERKIN)

    call_kwargs = mock_gs.call_args.kwargs
    context_ids = [c["id"] for c in call_kwargs["context"]]
    assert "style_sample" not in context_ids


def test_prompt_mentions_imita_when_style_sample_given():
    """When style_sample is provided, the prompt instructs the LLM to imitate the style."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_GHERKIN, style_sample="some style")

    call_kwargs = mock_gs.call_args.kwargs
    assert "imita" in call_kwargs["prompt"].lower() or "style_sample" in call_kwargs["prompt"].lower()


def test_prompt_uses_standard_conventions_when_no_style_sample():
    """When style_sample is absent, the prompt mentions standard Playwright conventions."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_GHERKIN)

    call_kwargs = mock_gs.call_args.kwargs
    assert "estándar" in call_kwargs["prompt"] or "convenciones" in call_kwargs["prompt"]


# ---------------------------------------------------------------------------
# Gherkin vs steps both work
# ---------------------------------------------------------------------------

def test_gherkin_case_is_included_in_context():
    """A case with 'gherkin' has its gherkin text passed into the context."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_GHERKIN)

    call_kwargs = mock_gs.call_args.kwargs
    case_ctx = next(c for c in call_kwargs["context"] if c["id"] == "case")
    assert "Given" in case_ctx["content"] or "Login exitoso" in case_ctx["content"]


def test_steps_case_is_included_in_context():
    """A case with 'steps' has those steps passed into the context."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_STEPS)

    call_kwargs = mock_gs.call_args.kwargs
    case_ctx = next(c for c in call_kwargs["context"] if c["id"] == "case")
    assert "Add to cart" in case_ctx["content"] or "Navigate to product page" in case_ctx["content"]


# ---------------------------------------------------------------------------
# Fallback: LLM returns None
# ---------------------------------------------------------------------------

def test_degrades_to_fallback_when_llm_returns_none():
    """generate_structured → None → returns a non-empty .spec.ts fallback, never raises."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=_CASE_GHERKIN)

    assert isinstance(result, dict)
    assert result["code"]  # non-empty
    assert result["filename"].endswith(".spec.ts")
    assert "LLM" in result["notes"] or "no disponible" in result["notes"]


def test_fallback_code_contains_case_title():
    """Fallback code includes the case title as a comment or test name."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=_CASE_GHERKIN)

    assert "Login exitoso" in result["code"]


def test_fallback_code_contains_fixme():
    """Fallback code includes test.fixme() to mark the test as pending."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=_CASE_STEPS)

    assert "test.fixme()" in result["code"]


def test_fallback_notes_mentions_llm_unavailable():
    """Fallback notes must state that LLM is unavailable."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=_CASE_STEPS)

    assert "LLM" in result["notes"] or "no disponible" in result["notes"]


def test_degrades_when_llm_returns_empty_code():
    """generate_structured returns dict with empty 'code' → treated as failure → fallback."""
    with patch("src.automation.agent.generate_structured", return_value={"code": "  ", "filename": "x.spec.ts", "notes": ""}):
        result = generate_playwright_test(case=_CASE_STEPS)

    # Should degrade to fallback since code is whitespace-only
    assert "test.fixme()" in result["code"]


def test_fallback_works_for_gherkin_case():
    """Fallback triggered for a gherkin case includes gherkin text as comment."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=_CASE_GHERKIN)

    assert "Login exitoso" in result["code"]
    assert result["filename"] == "login-exitoso.spec.ts"


def test_fallback_works_for_steps_case():
    """Fallback triggered for a steps case includes steps as comments."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=_CASE_STEPS)

    assert "Add to cart" in result["code"]
    assert result["filename"] == "add-to-cart.spec.ts"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_never_raises_on_none_case():
    """Passing None or empty dict as case must not raise."""
    with patch("src.automation.agent.generate_structured", return_value=None):
        result = generate_playwright_test(case=None)

    assert isinstance(result, dict)
    assert result["code"]


def test_filename_fallback_when_llm_returns_bad_filename():
    """If LLM returns a blank filename, it is derived from the case title."""
    llm_response = {**_LLM_RESPONSE, "filename": ""}
    with patch("src.automation.agent.generate_structured", return_value=llm_response):
        result = generate_playwright_test(case=_CASE_GHERKIN)

    assert result["filename"].endswith(".spec.ts")
    assert result["filename"] != ".spec.ts"


def test_notes_defaults_to_empty_string_when_llm_returns_non_string():
    """If LLM returns non-string notes, notes field defaults to empty string."""
    llm_response = {**_LLM_RESPONSE, "notes": 42}
    with patch("src.automation.agent.generate_structured", return_value=llm_response):
        result = generate_playwright_test(case=_CASE_GHERKIN)

    assert result["notes"] == ""


def test_on_failure_none_passed_to_generate_structured():
    """generate_structured must be called with on_failure='none' (degrade, not raise)."""
    with patch("src.automation.agent.generate_structured", return_value=_LLM_RESPONSE) as mock_gs:
        generate_playwright_test(case=_CASE_GHERKIN)

    call_kwargs = mock_gs.call_args.kwargs
    assert call_kwargs.get("on_failure") == "none"
