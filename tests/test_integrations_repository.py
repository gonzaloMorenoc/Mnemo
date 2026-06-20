import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from cryptography.fernet import Fernet  # noqa: E402
import psycopg  # noqa: E402

from src.jira.integrations_repository import IntegrationsRepository  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def repo(monkeypatch):
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    monkeypatch.setenv("MNEMO_SECRET_KEY", Fernet.generate_key().decode())
    return IntegrationsRepository(DBURL)


@pytest.fixture
def org():
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"int-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s, %s) returning id",
                        ("int-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def test_upsert_then_get_config_hides_token(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.upsert_jira_config(user_id=u, org_id=o, base_url="https://acme.atlassian.net",
                            email="a@b.c", token="secret-token", jql="issuetype = Bug")
    cfg = repo.get_jira_config(user_id=u, org_id=o)
    assert cfg["configured"] is True
    assert cfg["base_url"] == "https://acme.atlassian.net"
    assert "token" not in cfg


def test_get_credentials_decrypts(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.upsert_jira_config(user_id=u, org_id=o, base_url="https://acme.atlassian.net",
                            email="a@b.c", token="secret-token", jql="issuetype = Bug")
    creds = repo.get_jira_credentials(user_id=u, org_id=o)
    assert creds["token"] == "secret-token"


def test_non_member_rejected(repo, org):
    other = str(uuid.uuid4())
    with pytest.raises(PermissionError):
        repo.upsert_jira_config(user_id=other, org_id=org["org_id"], base_url="https://acme.atlassian.net",
                                email="a@b.c", token="t", jql="issuetype = Bug")
