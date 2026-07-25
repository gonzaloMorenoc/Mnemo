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


def test_todos_los_fallos_son_clasificables_por_el_motor():
    """Un fallo que no casa ningún patrón se queda en 'unknown' y ensucia el
    Defect DNA. Este test lo caza aquí (milisegundos) en vez de en la siembra."""
    from src.triage.patterns import classify_error

    for proyecto, fallos in FAILURE_CATALOG.items():
        for f in fallos:
            cats = classify_error(f.error_type, f.message or "", f.trace)
            assert cats, (
                f"{proyecto}/{f.test_name} no casa infra/locator/assertion → "
                "el motor lo dejaría sin clasificar")


def test_el_tramo_antiguo_usa_todo_el_catalogo():
    """Toda familia tiene que existir ANTES de la fase de etiquetado: una que nazca
    en el tramo reciente no llega a calibrar el motor y además se queda 'unknown'."""
    usados = {k for r in RUN_CALENDAR if r.days_ago > 30 for k in r.failure_keys}
    todos = {f.test_name for fallos in FAILURE_CATALOG.values() for f in fallos}
    faltan = todos - usados
    assert not faltan, f"fallos que solo aparecen tarde: {sorted(faltan)}"


def test_los_fallos_de_localizador_tienen_pasado_verde():
    """R3 (maintenance) exige que el test pasara antes y que el DOM haya cambiado.
    Sin ese pasado, el motor no puede clasificarlo y cae en 'unknown'."""
    from src.demo.demo_catalog import BASELINE_DOM
    from src.triage.patterns import classify_error

    for proyecto, fallos in FAILURE_CATALOG.items():
        for f in fallos:
            cats = classify_error(f.error_type, f.message or "", f.trace)
            if "locator" not in cats or "assertion" in cats:
                continue
            assert f.test_name in BASELINE_DOM, f"{f.test_name} sin DOM de referencia"
            assert f.dom and f.dom != BASELINE_DOM[f.test_name], (
                f"{f.test_name}: el DOM del fallo debe diferir del que tenía al pasar")
            previos = [r for r in RUN_CALENDAR if f.test_name in r.green_keys]
            fallando = [r for r in RUN_CALENDAR if f.test_name in r.failure_keys]
            assert previos, f"{f.test_name} nunca aparece pasando antes"
            assert max(r.days_ago for r in previos) > max(r.days_ago for r in fallando), (
                f"{f.test_name}: el run verde tiene que ser ANTERIOR al fallo")


def test_los_fallos_de_infraestructura_llegan_en_grupo():
    """R2 (infra) exige fallo masivo: al menos 3 errores de red en el mismo run."""
    from src.triage.patterns import classify_error

    def es_infra(nombre, proyecto):
        f = next(x for x in FAILURE_CATALOG[proyecto] if x.test_name == nombre)
        cats = classify_error(f.error_type, f.message or "", f.trace)
        return "infra" in cats

    infra_totales = {f.test_name for p, fallos in FAILURE_CATALOG.items()
                     for f in fallos if es_infra(f.test_name, p)}
    agrupados = set()
    for r in RUN_CALENDAR:
        del_run = [k for k in r.failure_keys if es_infra(k, r.project)]
        if len(del_run) >= 3:
            agrupados.update(del_run)
    assert infra_totales <= agrupados, (
        f"errores de red que van sueltos y quedarían sin clasificar: "
        f"{sorted(infra_totales - agrupados)}")
