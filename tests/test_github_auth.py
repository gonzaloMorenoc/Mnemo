import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.ci.github_auth import GitHubAppAuth, GitHubAppNotConfigured, GitHubAuthError


@pytest.fixture(scope="module")
def private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def test_app_jwt_has_iss_and_exp(private_key):
    tok = GitHubAppAuth(app_id="123", private_key=private_key).app_jwt()
    decoded = jwt.decode(tok, options={"verify_signature": False})
    assert decoded["iss"] == "123" and decoded["exp"] > decoded["iat"]
    assert decoded["exp"] - decoded["iat"] <= 600


def test_app_jwt_missing_config_raises():
    with pytest.raises(GitHubAuthError):
        GitHubAppAuth(app_id="", private_key="").app_jwt()


def test_installation_token_caches(private_key):
    calls = []

    class _Resp:
        status_code = 201
        def json(self):
            return {"token": "ghs_abc", "expires_at": "2999-01-01T00:00:00Z"}

    class _Sess:
        def post(self, *a, **k):
            calls.append(1)
            return _Resp()

    auth = GitHubAppAuth(app_id="1", private_key=private_key, session=_Sess())
    assert auth.installation_token("99") == "ghs_abc"
    assert auth.installation_token("99") == "ghs_abc"  # 2ª vez = cache
    assert len(calls) == 1


def test_installation_token_error_raises(private_key):
    class _Resp:
        status_code = 404
        def json(self):
            return {}

    class _Sess:
        def post(self, *a, **k):
            return _Resp()

    auth = GitHubAppAuth(app_id="1", private_key=private_key, session=_Sess())
    with pytest.raises(GitHubAuthError):
        auth.installation_token("99")


def test_installation_account_returns_login(private_key):
    class _Resp:
        status_code = 200
        def json(self):
            return {"account": {"login": "acme-corp"}}

    class _Sess:
        def get(self, *a, **k):
            return _Resp()

    auth = GitHubAppAuth(app_id="1", private_key=private_key, session=_Sess())
    assert auth.installation_account("99") == "acme-corp"


def test_installation_account_not_found_raises(private_key):
    class _Resp:
        status_code = 404
        def json(self):
            return {}

    class _Sess:
        def get(self, *a, **k):
            return _Resp()

    auth = GitHubAppAuth(app_id="1", private_key=private_key, session=_Sess())
    with pytest.raises(GitHubAuthError):
        auth.installation_account("99")


def test_installation_account_missing_app_raises_notconfigured():
    with pytest.raises(GitHubAppNotConfigured):
        GitHubAppAuth(app_id="", private_key="").installation_account("99")
