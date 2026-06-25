import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.certify.repository import CertificateRepository
from src.defects.repository import AssuranceRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def repos():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return CertificateRepository(DBURL), AssuranceRepository(DBURL)


@pytest.fixture
def org():
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"cert-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("cert-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
            cur.execute("insert into public.test_runs (org_id, project, source, commit_sha)"
                        " values (%s, 'web', 'playwright', 'sha-cert') returning id", (org_id,))
            run_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id, "run_id": run_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def test_get_run_meta(repos, org):
    crepo, _ = repos
    meta = crepo.get_run_meta(user_id=org["user_id"], run_id=org["run_id"])
    assert meta == {"org_id": org["org_id"], "project": "web", "commit_sha": "sha-cert"}
    assert crepo.get_run_meta(user_id=str(uuid.uuid4()), run_id=org["run_id"]) is None  # no-miembro


def test_save_then_get_certificate(repos, org):
    crepo, _ = repos
    u, o, r = org["user_id"], org["org_id"], org["run_id"]
    cid = crepo.save_certificate(user_id=u, org_id=o, run_id=r,
                                 canonical_json={"verdict": "apto"}, signature="sig",
                                 verdict="apto", risk_score=0, sign_offs=[],
                                 mnemo_version="0.4.0", model_version="llama3")
    assert cid
    got = crepo.get_certificate(user_id=u, run_id=r)
    assert got["verdict"] == "apto" and got["signature"] == "sig" and got["canonical_json"] == {"verdict": "apto"}
    assert crepo.get_certificate(user_id=str(uuid.uuid4()), run_id=r) is None  # no-miembro


def test_save_certificate_non_member_rejected(repos, org):
    crepo, _ = repos
    with pytest.raises((PermissionError, ValueError)):
        crepo.save_certificate(user_id=str(uuid.uuid4()), org_id=org["org_id"], run_id=org["run_id"],
                               canonical_json={}, signature="s", verdict="apto", risk_score=0,
                               sign_offs=[], mnemo_version="v", model_version="m")


def test_signature_survives_jsonb_roundtrip(repos, org):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from src.certify.certificate import build_certificate
    from src.certify.signing import canonical_json, sign, verify
    crepo, _ = repos
    u, o, r = org["user_id"], org["org_id"], org["run_id"]
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    cert = build_certificate(
        run={"org_id": o, "project": "web", "commit_sha": "sha-cert", "run_id": r},
        verdicts=[{"failure_id": "f1", "category": "real", "confidence": 0.93333333333,
                   "rule_applied": "R5_real_novel", "requires_approval": False}],
        sign_offs=[], mnemo_version="0.4.0", model_version="m", created_at="2026-06-25T00:00:00Z")
    sig = sign(canonical_json(cert), priv_pem)
    crepo.save_certificate(user_id=u, org_id=o, run_id=r, canonical_json=cert, signature=sig,
                           verdict=cert["verdict"], risk_score=cert["risk_score"],
                           sign_offs=cert["sign_offs"], mnemo_version="0.4.0", model_version="m")
    stored = crepo.get_certificate(user_id=u, run_id=r)
    assert verify(canonical_json(stored["canonical_json"]), stored["signature"], pub_pem) is True
