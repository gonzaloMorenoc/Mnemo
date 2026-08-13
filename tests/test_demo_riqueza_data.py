"""Invariantes de la riqueza: los proyectos del arco quedan intactos por construcción."""
from src.demo.riqueza_data import ASSETS, FAMILY_TRIAGE, KB_ITEMS, PROTECTED, WEEKLY_PROFILE


def test_los_protegidos_solo_reciben_runs_verdes():
    for p in PROTECTED:
        assert WEEKLY_PROFILE[p]["fail_weeks"] == 0, f"{p} debe ser solo-verde"


def test_solo_dos_proyectos_llevan_fallos():
    con_fallos = [p for p, prof in WEEKLY_PROFILE.items() if prof["fail_weeks"]]
    assert sorted(con_fallos) == ["portal-clientes", "tienda-online"]


def test_ningun_item_de_kb_toca_los_protegidos():
    assert not [i for i in KB_ITEMS if i["project"] in PROTECTED]


def test_kb_titulos_unicos_y_kinds_validos():
    titulos = [i["title"] for i in KB_ITEMS]
    assert len(titulos) == len(set(titulos))
    from src.knowledge.repository import KINDS
    assert all(i["kind"] in KINDS for i in KB_ITEMS)


def test_triaje_once_entradas_todas_con_razon():
    # Once objetivos para dejar exactamente DOS unknown en la org real; las entradas
    # cuyo objetivo ya esté etiquetado no hacen nada (matching solo sobre unknown).
    assert len(FAMILY_TRIAGE) == 11
    assert all(reason.strip() for _, _, reason in FAMILY_TRIAGE)
    assert all(label in ("real", "flaky", "infra", "maintenance")
               for _, label, _ in FAMILY_TRIAGE)


def test_assets_paths_unicos():
    paths = [a["path"] for a in ASSETS]
    assert len(paths) == len(set(paths)) and len(paths) >= 10
