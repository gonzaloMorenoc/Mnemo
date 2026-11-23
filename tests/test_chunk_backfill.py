"""Relleno automático de fragmentos al arrancar (sustituye a `reembed --only-knowledge`)."""
from contextlib import contextmanager

import src.knowledge.chunk_backfill as backfill

LONG = "palabra " * 400   # no cabe en un embedding único → se trocea
SHORT = "breve"


class _Cursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if "to_regclass" in sql:
            self._rows = [{"ok": self.db["table"]}]
        elif "from public.qa_knowledge k" in sql:
            self._rows = list(self.db["items"])
        elif sql.startswith("delete"):
            self.db["deleted"].append(params[0])

    def executemany(self, sql, rows):
        self.db["inserted"].extend(rows)

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, db):
        self.db = db

    def cursor(self, row_factory=None):
        return _Cursor(self.db)

    def commit(self):
        self.db["commits"] += 1


class _Embedder:
    def embed(self, text):
        return [0.0] * 3


def _db(items, table=True):
    return {"table": table, "items": items, "deleted": [], "inserted": [], "commits": 0}


def _factory(db):
    @contextmanager
    def factory():
        yield _Conn(db)
    return factory


def test_rellena_solo_los_items_largos():
    db = _db([{"id": "k1", "org_id": "o1", "title": "t", "challenge": LONG, "approach": None},
              {"id": "k2", "org_id": "o1", "title": "t", "challenge": SHORT, "approach": None}])
    assert backfill.backfill_missing_chunks(_factory(db), _Embedder()) == 1
    assert db["deleted"] == ["k1"]
    assert db["inserted"] and all(row[0] == "k1" and row[1] == "o1" for row in db["inserted"])


def test_sin_la_migracion_033_no_hace_nada():
    db = _db([{"id": "k1", "org_id": "o1", "title": "t", "challenge": LONG, "approach": None}],
             table=False)
    assert backfill.backfill_missing_chunks(_factory(db), _Embedder()) == 0
    assert db["inserted"] == []


def test_se_desactiva_por_variable(monkeypatch):
    monkeypatch.setenv(backfill.ENV_SWITCH, "false")
    assert backfill.start_backfill_in_background(_factory(_db([])), _Embedder) is None


def test_un_fallo_no_rompe_el_arranque(monkeypatch, caplog):
    monkeypatch.delenv(backfill.ENV_SWITCH, raising=False)

    @contextmanager
    def broken():
        raise RuntimeError("bd caída")
        yield  # pragma: no cover

    thread = backfill.start_backfill_in_background(broken, _Embedder)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert "relleno de fragmentos falló" in caplog.text
