"""Continuidad: repositorio de actas y servicio de emisión (auditoría 12-ago, paso 3).

Los tests del repositorio son integration (BD real, fixtures propios con cleanup);
los del servicio son unit con claves Ed25519 generadas al vuelo.
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.continuity.repository import ContinuityRepository  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture()
def org_con_admin():
    """Org nueva con un usuario owner. Cleanup total al salir (esto es la BD real)."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"cont-{user[:8]}@test.internal"))
        # El trigger create_owner_membership ya da de alta al creador como owner:
        # insertarla a mano viola memberships_pkey.
        cur.execute("insert into public.organizations (name, created_by)"
                    " values (%s,%s) returning id", ("cont-org-" + user[:8], user))
        org = str(cur.fetchone()[0])
        conn.commit()
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


@pytest.mark.integration
def test_save_y_latest_devuelven_el_acta_mas_reciente(org_con_admin):
    repo = ContinuityRepository()
    org, user = org_con_admin["org"], org_con_admin["user"]
    for score in (10, 42):  # dos actas: latest debe ser la segunda
        assert repo.save_act(
            user_id=user, org_id=org, project="checkout-suite",
            canonical_json={"schema": "mnemo.traspaso.v1", "score": score},
            signature="firma==", score=score, created_by=user) is not None
    act = repo.latest_act(user_id=user, org_id=org, project="checkout-suite")
    assert act["score"] == 42
    assert act["canonical_json"]["schema"] == "mnemo.traspaso.v1"
    assert act["signature"] == "firma=="
    assert isinstance(act["created_at"], str) and "T" in act["created_at"]


@pytest.mark.integration
def test_latest_sin_actas_es_none(org_con_admin):
    repo = ContinuityRepository()
    assert repo.latest_act(user_id=org_con_admin["user"],
                           org_id=org_con_admin["org"], project="nada") is None


@pytest.mark.integration
def test_no_miembro_no_guarda_ni_lee(org_con_admin):
    repo = ContinuityRepository()
    extrano = str(uuid.uuid4())
    assert repo.save_act(user_id=extrano, org_id=org_con_admin["org"],
                         project="p", canonical_json={}, signature="s",
                         score=1, created_by=extrano) is None
    assert repo.latest_act(user_id=extrano, org_id=org_con_admin["org"],
                           project="p") is None


@pytest.mark.integration
def test_is_org_admin_distingue_roles(org_con_admin):
    repo = ContinuityRepository()
    org = org_con_admin["org"]
    assert repo.is_org_admin(user_id=org_con_admin["user"], org_id=org) is True
    assert repo.is_org_admin(user_id=str(uuid.uuid4()), org_id=org) is False


# ---------------------------------------------------------------------------
# Servicio de emisión: unit con claves Ed25519 generadas al vuelo (sin BD).
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from src.certify.share import share_blob  # noqa: E402
from src.certify.signing import canonical_json  # noqa: E402
from src.certify.signing import verify as sig_verify  # noqa: E402
from src.continuity.service import ContinuityService  # noqa: E402


def _keys():
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


_IDX = {"score": 42,
        "dimensions": [{"key": "oficio", "label": "Oficio del proyecto",
                        "num": 2, "den": 4, "ratio": 0.5, "weight": 0.25}],
        "inventario": {"familias": 3}}


def _service(admin=True, projects=("checkout-suite",)):
    priv, pub = _keys()
    repo = MagicMock()
    repo.is_org_admin.return_value = admin
    repo.save_act.return_value = {"id": "a1"}
    svc = ContinuityService(repo=repo, private_key=priv, public_key=pub,
                            mnemo_version="test",
                            index_fn=lambda **kw: _IDX,
                            projects_fn=lambda **kw: list(projects))
    return svc, repo, pub


def test_emitir_firma_y_verifica():
    svc, repo, pub = _service()
    out = svc.emit_handover(user_id="u", org_id="o", project="checkout-suite",
                            created_at="2026-08-13T10:00:00Z")
    cj = out["canonical_json"]
    assert cj["schema"] == "mnemo.traspaso.v1"
    assert cj["continuity"]["score"] == 42
    assert cj["emitted_by"] == "u"
    assert sig_verify(canonical_json(cj), out["signature"], pub) is True
    assert out["share"] == share_blob(cj, out["signature"])
    repo.save_act.assert_called_once()
    assert repo.save_act.call_args.kwargs["score"] == 42


def test_un_byte_cambiado_invalida_la_firma():
    svc, _, pub = _service()
    out = svc.emit_handover(user_id="u", org_id="o", project="checkout-suite",
                            created_at="2026-08-13T10:00:00Z")
    manipulado = {**out["canonical_json"], "project": "otro"}
    assert sig_verify(canonical_json(manipulado), out["signature"], pub) is False


def test_sin_admin_permission_error():
    svc, _, _ = _service(admin=False)
    with pytest.raises(PermissionError):
        svc.emit_handover(user_id="u", org_id="o", project="checkout-suite",
                          created_at="2026-08-13T10:00:00Z")


def test_proyecto_desconocido_value_error():
    svc, _, _ = _service(projects=("otro",))
    with pytest.raises(ValueError):
        svc.emit_handover(user_id="u", org_id="o", project="checkout-suite",
                          created_at="2026-08-13T10:00:00Z")


def test_el_acta_cabe_en_un_enlace():
    # share_blob devuelve "" si el sobre pasa de 4096: un acta que no cabe en un
    # enlace no se puede repartir, que es todo el sentido de firmarla.
    svc, _, _ = _service()
    out = svc.emit_handover(user_id="u", org_id="o", project="checkout-suite",
                            created_at="2026-08-13T10:00:00Z")
    assert out["share"] != ""


def test_latest_regenera_el_share():
    svc, repo, _ = _service()
    repo.latest_act.return_value = {
        "canonical_json": {"schema": "mnemo.traspaso.v1"}, "signature": "sig",
        "score": 42, "project": "checkout-suite", "created_at": "2026-08-13T10:00:00Z"}
    out = svc.latest_handover(user_id="u", org_id="o", project="checkout-suite")
    assert out["share"] == share_blob({"schema": "mnemo.traspaso.v1"}, "sig")


def test_latest_sin_acta_none():
    svc, repo, _ = _service()
    repo.latest_act.return_value = None
    assert svc.latest_handover(user_id="u", org_id="o", project="p") is None
