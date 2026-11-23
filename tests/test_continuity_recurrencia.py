"""«Recurrente» = la familia falló en ≥2 runs DISTINTOS del proyecto (auditoría
23-nov, #19). Antes se usaba occurrence_count, que suma un fallo por test: un
único run con 30 tests caídos por el mismo error de entorno contaba como
recurrente en la dimensión de más peso del índice. Test puro: sin BD."""
from src.continuity.index import (
    MIN_RUNS_RECURRENTE,
    RECURRENCE_CRITERION,
    _Q_FAMILIAS,
    _dim_memoria,
    recurrentes,
)


def _fam(run_count, occurrence_count=99, con_conocimiento=False):
    return {"id": "f", "label": "real", "run_count": run_count,
            "occurrence_count": occurrence_count, "con_conocimiento": con_conocimiento}


def test_muchos_fallos_en_un_solo_run_no_es_recurrente():
    assert recurrentes([_fam(1, occurrence_count=30)]) == []


def test_dos_runs_distintos_si_es_recurrente():
    fam = _fam(MIN_RUNS_RECURRENTE, occurrence_count=2)
    assert recurrentes([fam]) == [fam]


def test_la_consulta_cuenta_runs_distintos_del_proyecto():
    sql = " ".join(_Q_FAMILIAS.split()).lower()
    assert "count(distinct fl.run_id)" in sql
    assert "tr.project = %(proj)s" in sql


def test_la_dimension_lleva_el_criterio_firmado():
    dim = _dim_memoria([_fam(2, con_conocimiento=True), _fam(3), _fam(1)])
    assert (dim["num"], dim["den"]) == (1, 2)
    assert dim["criterio"] == RECURRENCE_CRITERION
