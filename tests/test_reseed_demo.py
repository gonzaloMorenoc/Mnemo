import importlib.util
import pathlib

# Carga el script como módulo (vive en scripts/, no en un paquete).
_SPEC = importlib.util.spec_from_file_location(
    "reseed_demo", pathlib.Path(__file__).parent.parent / "scripts" / "reseed_demo.py")
reseed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reseed)


def test_confirmed_solo_acepta_reseed_exacto():
    assert reseed._confirmed("reseed")
    assert reseed._confirmed("  ReSeed  ")
    assert not reseed._confirmed("no")
    assert not reseed._confirmed("reseed please")


def test_main_cancela_sin_borrar(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://dummy")
    called = {"deleted": False}
    monkeypatch.setattr(reseed, "_delete_demo_orgs", lambda *a, **k: called.__setitem__("deleted", True) or 0)
    rc = reseed.main(["reseed_demo.py", "user-uuid"], ask=lambda _: "no")
    assert rc == 1
    assert called["deleted"] is False  # sin confirmar, NO se borra nada
