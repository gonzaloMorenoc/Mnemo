"""Tests for src/xray/client.py and src/xray/config.py (all HTTP mocked).

No real Xray credentials are needed.  ``requests`` calls are intercepted via
``unittest.mock.patch``.  The crypto round-trip test uses the Fernet key from
the environment variable MNEMO_SECRET_KEY (set to a safe test value in this
module so tests are self-contained).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Ensure a valid MNEMO_SECRET_KEY is present for crypto tests.
# This is done BEFORE importing anything that calls _fernet() at import time.
# ---------------------------------------------------------------------------
_TEST_KEY = Fernet.generate_key().decode()
os.environ.setdefault("MNEMO_SECRET_KEY", _TEST_KEY)

from src.xray.client import XrayClient, XrayImportError, XrayNotConfigured  # noqa: E402
from src.xray.config import XrayConfig  # noqa: E402
from src.jira.crypto import decrypt_token, encrypt_token  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_CLOUD_CREDS: Dict[str, str] = {
    "base_url": "https://xray.cloud.getxray.app",
    "client_id": "cid-test",
    "client_secret": "csec-test",
    "mode": "cloud",
}

_SERVER_CREDS: Dict[str, str] = {
    "base_url": "https://jira.acme.com",
    "client_id": "user@acme.com",
    "client_secret": "jira-api-token",
    "mode": "server",
}

_PLAN_MANUAL: Dict[str, Any] = {
    "summary": "Test plan",
    "cases": [
        {
            "title": "Pago exitoso",
            "priority": "critica",
            "steps": ["Abrir checkout", "Introducir tarjeta"],
            "expected": "Transacción aprobada",
        },
        {
            "title": "Pago rechazado",
            "priority": "alta",
            "steps": ["Abrir checkout", "Introducir tarjeta expirada"],
            "expected": "Mensaje de error",
        },
    ],
}

_PLAN_GHERKIN: Dict[str, Any] = {
    "summary": "Gherkin plan",
    "cases": [
        {
            "title": "Login exitoso",
            "gherkin": (
                "Scenario: Login exitoso\n"
                "  Given el usuario está en la pantalla de login\n"
                "  When introduce credenciales válidas\n"
                "  Then ve el dashboard"
            ),
        },
        {
            "title": "Login fallido",
            "gherkin": (
                "Scenario: Login fallido\n"
                "  Given el usuario está en la pantalla de login\n"
                "  When introduce credenciales inválidas\n"
                "  Then ve mensaje de error"
            ),
        },
    ],
}


def _client_with_creds(creds: Dict[str, str]) -> XrayClient:
    """Build an XrayClient pre-loaded with creds so the DB is never called."""
    c = XrayClient.__new__(XrayClient)
    c._org_id = "org-test"
    c._config = MagicMock()
    c._creds = creds
    return c


def _mock_bearer_response(token: str = "fake-bearer-token") -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = token  # Xray Cloud returns the token as a JSON string
    return mock


def _mock_gherkin_response(keys: list) -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = {
        "updatedOrCreatedTests": [{"key": k, "id": f"id-{k}"} for k in keys]
    }
    return mock


def _mock_graphql_response(key: str) -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = {
        "data": {"createTest": {"test": {"jira": {"key": key}}, "warnings": []}}
    }
    return mock


# ===========================================================================
# Authentication
# ===========================================================================


class TestAuthenticate:
    def test_cloud_auth_posts_client_credentials(self):
        """Cloud auth sends client_id + client_secret to Xray authenticate endpoint."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response("my-token")

        with patch("src.xray.client.requests.post", return_value=auth_resp) as mock_post:
            bearer = client._authenticate(_CLOUD_CREDS)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "xray.cloud.getxray.app" in call_kwargs[0][0]
        body = call_kwargs[1]["json"]
        assert body["client_id"] == "cid-test"
        assert body["client_secret"] == "csec-test"
        assert bearer == "Bearer my-token"

    def test_cloud_auth_raises_on_failure(self):
        """A non-2xx auth response raises XrayImportError."""
        client = _client_with_creds(_CLOUD_CREDS)
        err_resp = MagicMock()
        err_resp.ok = False
        err_resp.status_code = 401
        err_resp.text = "Unauthorized"

        with patch("src.xray.client.requests.post", return_value=err_resp):
            with pytest.raises(XrayImportError, match="authentication failed"):
                client._authenticate(_CLOUD_CREDS)

    def test_server_auth_returns_basic_header(self):
        """Server mode returns a Basic-auth header without an HTTP call."""
        client = _client_with_creds(_SERVER_CREDS)
        with patch("src.xray.client.requests.post") as mock_post:
            bearer = client._authenticate(_SERVER_CREDS)

        mock_post.assert_not_called()
        assert bearer.startswith("Basic ")
        # Decode and verify content
        import base64
        decoded = base64.b64decode(bearer[6:]).decode()
        assert decoded == "user@acme.com:jira-api-token"

    def test_cloud_auth_non_json_body_raises_import_error(self):
        """C2: if the auth response body is not valid JSON, raise XrayImportError (not ValueError)."""
        client = _client_with_creds(_CLOUD_CREDS)
        bad_resp = MagicMock()
        bad_resp.ok = True
        bad_resp.json.side_effect = ValueError("No JSON object could be decoded")
        bad_resp.text = "not-json"

        with patch("src.xray.client.requests.post", return_value=bad_resp):
            with pytest.raises(XrayImportError, match="not valid JSON"):
                client._authenticate(_CLOUD_CREDS)


# ===========================================================================
# Gherkin import
# ===========================================================================


class TestImportGherkin:
    def _run(self, creds: Dict[str, str], keys: list, project_key: str = "ACME") -> list:
        client = _client_with_creds(creds)
        # Server mode authenticates without HTTP; cloud mode makes one auth call.
        auth_resp = _mock_bearer_response()
        gherkin_resp = _mock_gherkin_response(keys)

        if creds["mode"] == "server":
            # No auth HTTP call for server mode — only the import call.
            with patch(
                "src.xray.client.requests.post",
                return_value=gherkin_resp,
            ):
                return client.import_plan(
                    plan=_PLAN_GHERKIN,
                    case_format="gherkin",
                    project_key=project_key,
                )
        else:
            with patch(
                "src.xray.client.requests.post",
                side_effect=[auth_resp, gherkin_resp],
            ):
                return client.import_plan(
                    plan=_PLAN_GHERKIN,
                    case_format="gherkin",
                    project_key=project_key,
                )

    def test_cloud_gherkin_returns_keys(self):
        """Cloud gherkin import returns the keys from updatedOrCreatedTests."""
        keys = self._run(_CLOUD_CREDS, ["ACME-10", "ACME-11"])
        assert keys == ["ACME-10", "ACME-11"]

    def test_server_gherkin_returns_keys(self):
        """Server gherkin import returns the keys from the response."""
        keys = self._run(_SERVER_CREDS, ["PROJ-5", "PROJ-6"], project_key="PROJ")
        assert keys == ["PROJ-5", "PROJ-6"]

    def test_gherkin_builds_feature_file(self):
        """The .feature file posted contains the Scenario text from each case."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        gherkin_resp = _mock_gherkin_response(["ACME-1"])

        captured: Dict[str, Any] = {}

        def _side_effect(url, **kwargs):
            # First call is auth (no files), second is the feature import.
            if "files" in kwargs:
                captured["url"] = url
                captured["files"] = kwargs["files"]
                return gherkin_resp
            return auth_resp

        with patch("src.xray.client.requests.post", side_effect=_side_effect):
            client.import_plan(plan=_PLAN_GHERKIN, case_format="gherkin", project_key="ACME")

        assert "files" in captured, "feature import call was not made"
        file_tuple = captured["files"]["file"]
        feature_bytes = file_tuple[1]  # ("plan.feature", <bytes>, "text/plain")
        feature_text = feature_bytes.decode() if isinstance(feature_bytes, bytes) else feature_bytes
        assert "Scenario: Login exitoso" in feature_text
        assert "Scenario: Login fallido" in feature_text
        assert "Given" in feature_text

    def test_gherkin_posts_to_feature_endpoint(self):
        """Cloud gherkin import posts to the /import/feature endpoint."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        gherkin_resp = _mock_gherkin_response(["ACME-1"])

        urls: list = []

        def _side_effect(url, **kwargs):
            urls.append(url)
            if "files" in kwargs:
                return gherkin_resp
            return auth_resp

        with patch("src.xray.client.requests.post", side_effect=_side_effect):
            client.import_plan(plan=_PLAN_GHERKIN, case_format="gherkin", project_key="ACME")

        assert any("import/feature" in u for u in urls)

    def test_gherkin_raises_on_api_error(self):
        """A non-2xx feature-import response raises XrayImportError."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        err_resp = MagicMock()
        err_resp.ok = False
        err_resp.status_code = 400
        err_resp.text = "Bad project key"

        with patch("src.xray.client.requests.post", side_effect=[auth_resp, err_resp]):
            with pytest.raises(XrayImportError, match="feature import failed"):
                client.import_plan(plan=_PLAN_GHERKIN, case_format="gherkin", project_key="BAD")

    def test_gherkin_empty_cases_returns_empty(self):
        """A plan with no cases returns [] without making import calls."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()

        with patch("src.xray.client.requests.post", return_value=auth_resp) as mock_post:
            result = client.import_plan(plan={"cases": []}, case_format="gherkin")

        assert result == []
        # Only auth call should happen (zero or one call; import should not happen)
        for call in mock_post.call_args_list:
            url = call[0][0] if call[0] else ""
            assert "import/feature" not in url

    def test_gherkin_non_json_response_raises_import_error(self):
        """C3: if the gherkin import response body is not valid JSON, raise XrayImportError."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        bad_import_resp = MagicMock()
        bad_import_resp.ok = True
        bad_import_resp.json.side_effect = ValueError("No JSON")
        bad_import_resp.text = "Internal Server Error"

        with patch("src.xray.client.requests.post", side_effect=[auth_resp, bad_import_resp]):
            with pytest.raises(XrayImportError, match="non-JSON"):
                client.import_plan(plan=_PLAN_GHERKIN, case_format="gherkin", project_key="ACME")


# ===========================================================================
# Manual test creation
# ===========================================================================


class TestImportManual:
    def _run(self, creds: Dict[str, str], keys: list) -> list:
        client = _client_with_creds(creds)
        auth_resp = _mock_bearer_response()
        graphql_resps = [_mock_graphql_response(k) for k in keys]

        with patch(
            "src.xray.client.requests.post",
            side_effect=[auth_resp, *graphql_resps],
        ):
            return client.import_plan(
                plan=_PLAN_MANUAL,
                case_format="manual",
                project_key="ACME",
            )

    def test_cloud_manual_returns_sorted_keys(self):
        """Cloud manual import creates one Test per case and returns sorted keys."""
        keys = self._run(_CLOUD_CREDS, ["ACME-2", "ACME-3"])
        assert keys == ["ACME-2", "ACME-3"]

    def test_cloud_manual_posts_graphql_mutation(self):
        """Cloud manual import posts the createTest GraphQL mutation per case."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        gql_resps = [_mock_graphql_response(k) for k in ["ACME-4", "ACME-5"]]

        posted_bodies = []

        def _capture(url, *, json=None, **kwargs):
            if json is not None:
                posted_bodies.append({"url": url, "body": json})
            return gql_resps.pop(0) if posted_bodies and "graphql" in url else auth_resp

        with patch("src.xray.client.requests.post", side_effect=[auth_resp, *gql_resps]):
            client.import_plan(plan=_PLAN_MANUAL, case_format="manual", project_key="ACME")

    def test_cloud_manual_sends_steps_in_payload(self):
        """Each case's steps appear in the GraphQL mutation variables."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        gql_resp1 = _mock_graphql_response("ACME-1")
        gql_resp2 = _mock_graphql_response("ACME-2")

        captured_bodies: list = []
        gql_responses = [gql_resp1, gql_resp2]

        def _intercept(url, **kwargs):
            if "graphql" in url:
                captured_bodies.append(kwargs.get("json", {}))
                return gql_responses.pop(0)
            return auth_resp

        with patch("src.xray.client.requests.post", side_effect=_intercept):
            client.import_plan(plan=_PLAN_MANUAL, case_format="manual", project_key="ACME")

        assert len(captured_bodies) == 2, "Expected one GraphQL call per case"
        for body in captured_bodies:
            assert "steps" in body.get("variables", {})
            steps = body["variables"]["steps"]
            assert isinstance(steps, list)
            assert len(steps) > 0

    def test_server_manual_posts_to_rest_api(self):
        """Server manual import posts to /rest/api/2/issue."""
        client = _client_with_creds(_SERVER_CREDS)
        auth_resp = MagicMock()  # server doesn't auth via HTTP — but we still call _authenticate
        # For server mode _authenticate() doesn't call requests.post,
        # so we only need the 2 issue-create calls.
        issue_resp1 = MagicMock()
        issue_resp1.ok = True
        issue_resp1.json.return_value = {"key": "PROJ-1"}
        issue_resp2 = MagicMock()
        issue_resp2.ok = True
        issue_resp2.json.return_value = {"key": "PROJ-2"}

        with patch(
            "src.xray.client.requests.post",
            side_effect=[issue_resp1, issue_resp2],
        ):
            result = client.import_plan(
                plan=_PLAN_MANUAL,
                case_format="manual",
                project_key="PROJ",
            )

        assert result == ["PROJ-1", "PROJ-2"]

    def test_manual_keys_are_sorted(self):
        """Returned keys are sorted lexicographically."""
        client = _client_with_creds(_CLOUD_CREDS)
        auth_resp = _mock_bearer_response()
        # Return keys out of order
        gql_resp1 = _mock_graphql_response("ACME-20")
        gql_resp2 = _mock_graphql_response("ACME-5")

        with patch(
            "src.xray.client.requests.post",
            side_effect=[auth_resp, gql_resp1, gql_resp2],
        ):
            result = client.import_plan(plan=_PLAN_MANUAL, case_format="manual", project_key="ACME")

        assert result == sorted(result)


# ===========================================================================
# XrayNotConfigured
# ===========================================================================


class TestNotConfigured:
    def test_raises_when_no_config(self):
        """import_plan raises XrayNotConfigured when no credentials are saved."""
        config_mock = MagicMock(spec=XrayConfig)
        config_mock.get_raw.return_value = None

        client = XrayClient(org_id="org-no-xray", config=config_mock)
        with pytest.raises(XrayNotConfigured, match="No hay configuración"):
            client.import_plan(plan=_PLAN_MANUAL, case_format="manual")

    def test_error_message_includes_org_id(self):
        """The XrayNotConfigured error message includes the org_id."""
        config_mock = MagicMock(spec=XrayConfig)
        config_mock.get_raw.return_value = None

        client = XrayClient(org_id="my-specific-org", config=config_mock)
        with pytest.raises(XrayNotConfigured, match="my-specific-org"):
            client.import_plan(plan=_PLAN_MANUAL, case_format="manual")


# ===========================================================================
# Gherkin feature builder
# ===========================================================================


class TestBuildFeature:
    def test_includes_all_scenarios(self):
        client = _client_with_creds(_CLOUD_CREDS)
        feature = client._build_feature(_PLAN_GHERKIN["cases"])
        assert "Login exitoso" in feature
        assert "Login fallido" in feature

    def test_fallback_scenario_for_missing_gherkin(self):
        """Cases without a 'gherkin' field get a synthetic Scenario block."""
        cases = [{"title": "Sin gherkin", "steps": ["paso1"]}]
        client = _client_with_creds(_CLOUD_CREDS)
        feature = client._build_feature(cases)
        assert "Scenario: Sin gherkin" in feature

    def test_feature_header_present(self):
        client = _client_with_creds(_CLOUD_CREDS)
        feature = client._build_feature(_PLAN_GHERKIN["cases"])
        assert feature.startswith("Feature:")


# ===========================================================================
# XrayConfig crypto round-trip (no DB)
# ===========================================================================


class TestXrayConfigCrypto:
    """Verify that the Fernet round-trip used by XrayConfig works correctly.

    These tests do NOT hit the database; they exercise only the crypto layer.
    """

    def test_encrypt_decrypt_round_trip(self):
        """A secret encrypted with encrypt_token can be decrypted back."""
        secret = "super-secret-client-secret-123"
        enc = encrypt_token(secret)
        assert enc != secret  # must not store plaintext
        assert decrypt_token(enc) == secret

    def test_different_plaintext_different_cipher(self):
        """Two different plaintexts produce different ciphertexts."""
        enc1 = encrypt_token("secret-a")
        enc2 = encrypt_token("secret-b")
        assert enc1 != enc2

    def test_tampered_cipher_raises_value_error(self):
        """A corrupted ciphertext causes XrayConfig._decrypt to raise ValueError."""
        config = XrayConfig.__new__(XrayConfig)
        config.db_url = "unused"
        with pytest.raises(ValueError, match="inválidas"):
            config._decrypt("not-a-valid-fernet-token")
