"""Qué texto se embebe de un test: lo que dice QUÉ prueba, no su sintaxis.

Embebiendo el código entero, los `import`, los selectores y la sintaxis del
framework dominaban el vector: medido en Demo MTP (30-sep), la regla «un cupón se
aplica una sola vez» quedaba más cerca de reembolsos.test.ts que de cupones.spec.ts,
y el hueco `regla_sin_test` era una moneda al aire. Los títulos de los tests y los
comentarios son lenguaje natural escrito por el equipo: es lo que casa con una regla
de negocio y con la descripción de un caso a automatizar.
"""
import re

_MAX_CHARS = 8000  # el mismo tope que el contenido guardado en test_assets

# test('…') · it("…") · describe(`…`) · test.describe('…') · Scenario('…') …
_TITLE = re.compile(
    r"""\b(?:test|it|describe|context|scenario|Scenario|Feature)\s*(?:\.\w+)?\s*\(\s*(['"`])(.+?)\1"""
)
_PY_TEST = re.compile(r"\bdef (test_\w+)")
# Comentario de línea o al final de una línea, con espacio tras el marcador: deja
# fuera los selectores ('#pagar') y las URLs ('https://…').
_COMMENT = re.compile(r"(?m)(?:^|\s)(?://|#)\s+(.+)$")
_PATH_SEP = re.compile(r"[/_.\-]+")


def asset_descriptor(path: str, content: str) -> str:
    """Ruta + títulos de tests + comentarios. Sin títulos reconocibles (helpers,
    page objects), el contenido tal cual: así ningún fichero se queda sin vector."""
    content = content or ""
    titles = [m.group(2) for m in _TITLE.finditer(content)]
    titles += [m.group(1)[len("test_"):].replace("_", " ") for m in _PY_TEST.finditer(content)]
    if not titles:
        return content[:_MAX_CHARS]
    comments = [m.group(1).strip() for m in _COMMENT.finditer(content)]
    name = _PATH_SEP.sub(" ", path or "").strip()
    return " · ".join([name, *titles, *comments])[:_MAX_CHARS]
