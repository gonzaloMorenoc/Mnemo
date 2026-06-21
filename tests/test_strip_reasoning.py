from src.llm.reasoning import strip_reasoning


def test_strips_think_block():
    assert strip_reasoning("<think>razonando...</think>\nLa respuesta") == "La respuesta"


def test_strips_multiline_think():
    assert strip_reasoning("<think>\nlinea1\nlinea2\n</think>respuesta") == "respuesta"


def test_noop_without_think():
    assert strip_reasoning("solo respuesta") == "solo respuesta"


def test_empty():
    assert strip_reasoning("") == ""


def test_strips_unclosed_think():
    assert strip_reasoning("<think>truncado a mitad sin cierre") == ""


def test_strips_unclosed_think_keeps_prefix():
    assert strip_reasoning("respuesta\n<think>colita sin cerrar") == "respuesta"


def test_strips_nested_then_open():
    assert strip_reasoning("<think>a<think>b</think>c answer") == ""
