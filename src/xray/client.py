"""XrayClient — import a Mnemo test plan into Jira/Xray.

API targets
-----------
Primary: **Xray Cloud** (most common SaaS setup).
Fallback: **Xray Server/DC** (self-hosted Jira with Xray plugin).

Xray Cloud endpoints used
~~~~~~~~~~~~~~~~~~~~~~~~~
1. Authentication::

       POST https://xray.cloud.getxray.app/api/v2/authenticate
       Content-Type: application/json
       Body: {"client_id": "...", "client_secret": "..."}
       → response body is a bearer token string (quoted JSON string)

2. Gherkin / Cucumber import::

       POST https://xray.cloud.getxray.app/api/v2/import/feature
       Authorization: Bearer <token>
       Content-Type: multipart/form-data
       Fields:
         file       — the .feature file bytes
         projectKey — Jira project key (e.g. "ACME")
       → {"updatedOrCreatedTests": [{"id":..., "key":"ACME-1", ...}], ...}

3. Manual test creation (one call per case)::

       POST https://xray.cloud.getxray.app/api/v2/graphql
       Authorization: Bearer <token>
       Content-Type: application/json
       Body: GraphQL mutation createTest
       → {"data": {"createTest": {"test": {"jira": {"key": "ACME-N"}}}}}

Xray Server/DC endpoints used
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Gherkin import::

       POST {jira_base}/rest/raven/2.0/import/feature?projectKey=...
       Authorization: Basic base64(email:token)
       Content-Type: multipart/form-data; file = .feature bytes

2. Manual test creation::

       POST {jira_base}/rest/api/2/issue
       Authorization: Basic base64(email:token)
       Content-Type: application/json
       Body: standard Jira issue create payload with issuetype "Test"
            + customfield for steps (Xray's "steps" field)

Assumptions / known gaps
~~~~~~~~~~~~~~~~~~~~~~~~
- The GraphQL mutation used for manual tests targets the Xray Cloud GraphQL API
  documented at https://us.xray.cloud.getxray.app/doc/graphql/createtest.doc.html
- For Server/DC manual tests: the "steps" custom field ID (`customfield_10007`)
  is the Xray default; self-hosted instances may differ.  Override via
  ``steps_field`` kwarg (not implemented here, post-MVP).
- No pagination for gherkin response (Xray returns all created keys at once).
- Bearer tokens from Xray Cloud expire; this client re-authenticates per call.
  Token caching is a future optimisation.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

import requests

from src.xray.config import XrayConfig

_CLOUD_AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
_CLOUD_GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
_CLOUD_FEATURE_URL = "https://xray.cloud.getxray.app/api/v2/import/feature"

_CREATE_TEST_MUTATION = """
mutation CreateTest($testType: UpdateTestTypeInput!, $steps: [CreateStepInput], $jira: JSON!) {
  createTest(testType: $testType, steps: $steps, jira: $jira) {
    test {
      jira(fields: ["key"])
    }
    warnings
  }
}
"""


class XrayNotConfigured(Exception):
    """Raised when no Xray credentials are saved for the given org."""


class XrayImportError(Exception):
    """Raised when the Xray API returns an unexpected error."""


class XrayClient:
    """Import a Mnemo test plan into Jira/Xray.

    Parameters
    ----------
    org_id:
        Mnemo org identifier; credentials are fetched from ``org_integrations``.
    config:
        ``XrayConfig`` instance.  Injected for testability; defaults to a new
        instance backed by ``DATABASE_URL``.
    _creds:
        Pre-loaded credentials dict (used by tests to bypass the DB entirely).
    """

    def __init__(
        self,
        org_id: str,
        config: Optional[XrayConfig] = None,
        *,
        _creds: Optional[Dict[str, str]] = None,
    ) -> None:
        self._org_id = org_id
        self._config = config or XrayConfig()
        self._creds: Optional[Dict[str, str]] = _creds  # can be None until first use

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def import_plan(
        self,
        *,
        plan: Dict[str, Any],
        case_format: str = "manual",
        project_key: str = "",
    ) -> List[str]:
        """Import all cases from *plan* into Jira/Xray.

        Parameters
        ----------
        plan:
            The test plan dict produced by ``generate_test_plan``.  Must
            contain a ``cases`` list; each case needs either ``steps``
            (manual) or ``gherkin`` (Gherkin).
        case_format:
            ``"manual"`` — create Test issues with step-by-step actions.
            ``"gherkin"`` — build a ``.feature`` file from the cases'
            ``gherkin`` fields and import it via the feature endpoint.
        project_key:
            Jira project key (e.g. ``"ACME"``).  Required for Gherkin import
            and for GraphQL manual creation.  If omitted, the client will skip
            project-key in manual creation (Jira may reject it).

        Returns
        -------
        list[str]
            Sorted list of created/updated Jira issue keys (e.g. ``["ACME-1", "ACME-2"]``).

        Raises
        ------
        XrayNotConfigured
            If no Xray credentials are configured for the org.
        XrayImportError
            If the Xray API returns an unexpected error.
        """
        creds = self._load_creds()
        mode = creds["mode"]
        bearer = self._authenticate(creds)

        cases = plan.get("cases") or []
        if not cases:
            return []

        if case_format == "gherkin":
            return self._import_gherkin(
                cases=cases,
                bearer=bearer,
                creds=creds,
                mode=mode,
                project_key=project_key,
            )
        return self._import_manual(
            cases=cases,
            bearer=bearer,
            creds=creds,
            mode=mode,
            project_key=project_key,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _load_creds(self) -> Dict[str, str]:
        if self._creds is not None:
            return self._creds
        creds = self._config.get_raw(org_id=self._org_id)
        if creds is None:
            raise XrayNotConfigured(
                f"No hay configuración de Xray para la org '{self._org_id}'. "
                "Configura client_id y client_secret primero."
            )
        self._creds = creds
        return creds

    def _authenticate(self, creds: Dict[str, str]) -> str:
        """Obtain a bearer token.

        For Cloud: POST to Xray authenticate endpoint with client_id/secret.
        For Server/DC: return a Basic-auth header value (no separate token).
        """
        mode = creds["mode"]
        if mode == "server":
            raw = f"{creds['client_id']}:{creds['client_secret']}"
            return "Basic " + base64.b64encode(raw.encode()).decode()

        # Cloud: exchange client_id+secret for bearer token
        auth_url = creds.get("auth_url") or _CLOUD_AUTH_URL
        resp = requests.post(
            auth_url,
            json={"client_id": creds["client_id"], "client_secret": creds["client_secret"]},
            timeout=30,
        )
        if not resp.ok:
            raise XrayImportError(
                f"Xray authentication failed ({resp.status_code}): {resp.text[:200]}"
            )
        # Xray Cloud returns a JSON-encoded string: "\"<token>\""
        try:
            parsed = resp.json()
            token = parsed if isinstance(parsed, str) else resp.text.strip().strip('"')
        except (ValueError, KeyError):
            raise XrayImportError(
                f"Xray authentication response is not valid JSON: {resp.text[:200]}"
            )
        return f"Bearer {token}"

    # ------------------------------------------------------------------
    # Gherkin import
    # ------------------------------------------------------------------

    def _build_feature(self, cases: List[Dict[str, Any]]) -> str:
        """Build a .feature file from the plan cases' gherkin fields."""
        lines: List[str] = ["Feature: Test Plan"]
        for case in cases:
            gherkin = case.get("gherkin") or ""
            if not gherkin:
                title = case.get("title", "Unnamed")
                gherkin = f"Scenario: {title}\n  Given a precondition\n  When an action\n  Then a result"
            # Normalise: strip blank-line prefix, ensure consistent indentation
            gherkin = gherkin.strip()
            lines.append("")
            lines.append(gherkin)
        return "\n".join(lines)

    def _import_gherkin(
        self,
        *,
        cases: List[Dict[str, Any]],
        bearer: str,
        creds: Dict[str, str],
        mode: str,
        project_key: str,
    ) -> List[str]:
        feature_text = self._build_feature(cases)
        headers = {"Authorization": bearer}

        if mode == "server":
            url = (
                creds["base_url"].rstrip("/")
                + f"/rest/raven/2.0/import/feature?projectKey={project_key}"
            )
            resp = requests.post(
                url,
                headers=headers,
                files={"file": ("plan.feature", feature_text.encode(), "text/plain")},
                timeout=60,
            )
        else:
            url = creds.get("feature_url") or _CLOUD_FEATURE_URL
            resp = requests.post(
                url,
                headers=headers,
                data={"projectKey": project_key} if project_key else {},
                files={"file": ("plan.feature", feature_text.encode(), "text/plain")},
                timeout=60,
            )

        if not resp.ok:
            raise XrayImportError(
                f"Xray feature import failed ({resp.status_code}): {resp.text[:300]}"
            )

        try:
            body = resp.json()
        except (ValueError, KeyError):
            raise XrayImportError(
                f"Xray feature import returned non-JSON response: {resp.text[:200]}"
            )
        # Cloud response: {"updatedOrCreatedTests": [{"id":..,"key":"X-1",...}], ...}
        tests = body.get("updatedOrCreatedTests") or body.get("testIssues") or []
        return sorted(t["key"] for t in tests if "key" in t)

    # ------------------------------------------------------------------
    # Manual test creation
    # ------------------------------------------------------------------

    def _import_manual(
        self,
        *,
        cases: List[Dict[str, Any]],
        bearer: str,
        creds: Dict[str, str],
        mode: str,
        project_key: str,
    ) -> List[str]:
        keys: List[str] = []
        for case in cases:
            key = self._create_manual_test(
                case=case,
                bearer=bearer,
                creds=creds,
                mode=mode,
                project_key=project_key,
            )
            if key:
                keys.append(key)
        return sorted(keys)

    def _create_manual_test(
        self,
        *,
        case: Dict[str, Any],
        bearer: str,
        creds: Dict[str, str],
        mode: str,
        project_key: str,
    ) -> Optional[str]:
        title = case.get("title", "Unnamed test")
        steps = case.get("steps") or []

        if mode == "server":
            return self._create_manual_server(
                title=title,
                steps=steps,
                bearer=bearer,
                creds=creds,
                project_key=project_key,
            )
        return self._create_manual_cloud(
            title=title,
            steps=steps,
            bearer=bearer,
            creds=creds,
            project_key=project_key,
        )

    def _create_manual_cloud(
        self,
        *,
        title: str,
        steps: List[Any],
        bearer: str,
        creds: Dict[str, str],
        project_key: str,
    ) -> Optional[str]:
        """Create a manual Test via Xray Cloud GraphQL."""
        step_inputs = [
            {"action": (s if isinstance(s, str) else s.get("action", str(s))), "result": ""}
            for s in steps
        ]
        jira_field: Dict[str, Any] = {"summary": title}
        if project_key:
            jira_field["project"] = {"key": project_key}

        payload = {
            "query": _CREATE_TEST_MUTATION,
            "variables": {
                "testType": {"name": "Manual"},
                "steps": step_inputs,
                "jira": json.dumps(jira_field),
            },
        }
        gql_url = creds.get("graphql_url") or _CLOUD_GRAPHQL_URL
        resp = requests.post(
            gql_url,
            headers={"Authorization": bearer, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if not resp.ok:
            raise XrayImportError(
                f"Xray GraphQL error ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        try:
            key = data["data"]["createTest"]["test"]["jira"]["key"]
        except (KeyError, TypeError):
            return None
        return key

    def _create_manual_server(
        self,
        *,
        title: str,
        steps: List[Any],
        bearer: str,
        creds: Dict[str, str],
        project_key: str,
    ) -> Optional[str]:
        """Create a manual Test via Jira Server REST API (Xray plugin)."""
        # Xray Server stores steps in customfield_10007 (default ID).
        step_list = [
            {
                "index": idx + 1,
                "fields": {
                    "Action": (s if isinstance(s, str) else s.get("action", str(s))),
                    "Expected Result": "",
                },
            }
            for idx, s in enumerate(steps)
        ]
        payload: Dict[str, Any] = {
            "fields": {
                "summary": title,
                "issuetype": {"name": "Test"},
                "customfield_10007": {"steps": step_list},
            }
        }
        if project_key:
            payload["fields"]["project"] = {"key": project_key}

        url = creds["base_url"].rstrip("/") + "/rest/api/2/issue"
        resp = requests.post(
            url,
            headers={"Authorization": bearer, "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        if not resp.ok:
            raise XrayImportError(
                f"Xray Server issue create failed ({resp.status_code}): {resp.text[:300]}"
            )
        try:
            return resp.json().get("key")
        except (ValueError, KeyError):
            raise XrayImportError(
                f"Xray Server issue create returned non-JSON response: {resp.text[:200]}"
            )
