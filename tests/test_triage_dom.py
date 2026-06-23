from src.triage.dom import dom_changed, normalize_dom


def test_normalize_collapses_whitespace():
    assert normalize_dom("<a>  x\n\t y </a>") == "<a> x y </a>"
    assert normalize_dom("") == ""


def test_dom_changed_true_when_normalized_differs():
    assert dom_changed("<a>x</a>", "<a>y</a>") is True


def test_dom_changed_false_when_normalized_equal():
    # difieren solo en espacios → iguales tras normalizar
    assert dom_changed("<a>x</a>", "  <a>x</a>  ") is False


def test_dom_changed_false_when_missing_either_side():
    assert dom_changed(None, "<a>x</a>") is False
    assert dom_changed("<a>x</a>", None) is False
    assert dom_changed("", "<a>x</a>") is False
