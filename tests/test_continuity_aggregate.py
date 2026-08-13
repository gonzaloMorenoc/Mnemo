"""La agregación del índice: renormalizar en vez de inventar ceros (paso 3)."""
from src.continuity.index import _aggregate


def test_agregacion_renormaliza_sin_denominador():
    dims = [
        {"key": "a", "num": 1, "den": 2, "ratio": 0.5, "weight": 0.5},
        {"key": "b", "num": 0, "den": 0, "ratio": None, "weight": 0.5},
    ]
    assert _aggregate(dims) == 50  # b se excluye; a manda con todo el peso


def test_agregacion_sin_datos_devuelve_none():
    # Ninguna dimensión medible: «sin datos suficientes», nunca un 0 que se leería
    # como «este proyecto está indocumentado».
    assert _aggregate([{"key": "a", "num": 0, "den": 0, "ratio": None, "weight": 1.0}]) is None


def test_agregacion_todo_cubierto_da_cien():
    assert _aggregate([{"key": "a", "num": 2, "den": 2, "ratio": 1.0, "weight": 0.7},
                       {"key": "b", "num": 1, "den": 1, "ratio": 1.0, "weight": 0.3}]) == 100
