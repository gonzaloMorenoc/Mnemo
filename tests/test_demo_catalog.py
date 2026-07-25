"""Calidad del catálogo de la demo: si estos datos no son creíbles, la demo tampoco."""
from src.demo.demo_catalog import FAILURE_CATALOG, PROYECTOS, RUN_CALENDAR

_RELLENO = ("foo", "bar", "test_1", "prueba", "asdf", "lorem")


def test_hay_fallos_para_todos_los_proyectos():
    assert set(FAILURE_CATALOG) == set(PROYECTOS)
    assert sum(len(v) for v in FAILURE_CATALOG.values()) >= 25


def test_cada_fallo_esta_completo_y_es_plausible():
    for proyecto, fallos in FAILURE_CATALOG.items():
        for f in fallos:
            assert f.status == "fail"
            assert f.error_type, f"{proyecto}/{f.test_name} sin error_type"
            assert len(f.message or "") > 15, f"{proyecto}/{f.test_name} con mensaje pobre"
            assert f.file and f.file.endswith((".ts", ".py", ".js")), f.test_name
            assert not any(r in f.test_name.lower() for r in _RELLENO), f.test_name


def test_las_firmas_no_se_repiten_entre_proyectos():
    # El fingerprint es (error_type, mensaje normalizado, top frame): dos fallos
    # idénticos en proyectos distintos mergearían en una sola familia y el Defect
    # DNA perdería la variedad que hace creíble la demo.
    firmas = [(f.error_type, f.message, f.trace)
              for fallos in FAILURE_CATALOG.values() for f in fallos]
    assert len(firmas) == len(set(firmas))


def test_el_calendario_cubre_tres_meses_con_mas_densidad_reciente():
    dias = sorted(r.days_ago for r in RUN_CALENDAR)
    assert len(RUN_CALENDAR) >= 40
    assert max(dias) >= 85 and min(dias) == 0
    recientes = [d for d in dias if d <= 30]
    antiguos = [d for d in dias if d > 60]
    assert len(recientes) > len(antiguos), "un equipo real acelera, no va a ritmo de metrónomo"


def test_el_calendario_solo_referencia_fallos_que_existen():
    for r in RUN_CALENDAR:
        disponibles = {f.test_name for f in FAILURE_CATALOG[r.project]}
        for key in r.failure_keys:
            assert key in disponibles, f"{r.commit} referencia un fallo inexistente: {key}"


def test_hay_runs_verdes_recientes_para_poder_firmar_en_verde():
    verdes = [r for r in RUN_CALENDAR if not r.failure_keys and r.days_ago <= 20]
    assert len(verdes) >= 3, "sin runs limpios recientes no hay acta 'apto' que enseñar"


def test_el_tramo_antiguo_tiene_fallos_que_generen_familias_que_etiquetar():
    # La calibración se gana etiquetando familias abiertas ANTES de las actas
    # recientes: si el tramo antiguo no falla, no hay nada que etiquetar.
    antiguos_con_fallos = [r for r in RUN_CALENDAR if r.days_ago > 30 and r.failure_keys]
    assert len(antiguos_con_fallos) >= 15


def test_los_commits_no_se_repiten():
    commits = [r.commit for r in RUN_CALENDAR]
    assert len(commits) == len(set(commits))
