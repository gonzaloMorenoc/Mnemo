from src.ingest.models import strip_ansi


def test_strip_ansi_removes_color_codes():
    assert strip_ansi("\x1b[31mError\x1b[0m: boom") == "Error: boom"


def test_strip_ansi_noop_on_plain_text():
    assert strip_ansi("plain") == "plain"


def test_strip_ansi_handles_empty():
    assert strip_ansi("") == ""
