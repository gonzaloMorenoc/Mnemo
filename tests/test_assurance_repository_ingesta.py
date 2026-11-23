"""AssuranceRepository — ingesta robusta (auditoría 23-nov: #5, #12, #18, #19b).

Tests unitarios con cursor simulado (los de repositorio contra BD son
`integration` y apuntan a prod: no se ejecutan aquí).
"""
from unittest.mock import MagicMock, patch

from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord


def _fake_pool(cur):
    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


def _repo():
    return AssuranceRepository(db_url="postgres://x")


def _sqls(cur):
    return [" ".join(str(c.args[0]).split()) for c in cur.execute.call_args_list]


def _item(fp: str, test_name: str = "t") -> IngestItem:
    rec = FailureRecord(test_name=test_name, error_type="E", message="m", trace=None,
                        project="p", source="junit")
    return IngestItem(rec=rec, fingerprint=fp, embedding=[0.1] * 384)


# ---------------------------------------------------------------------------
# #12 — familias: INSERT … ON CONFLICT y bloqueo en orden determinista
# ---------------------------------------------------------------------------

class TestFamilyUpsert:
    def test_new_family_insert_uses_on_conflict(self):
        cur = MagicMock()
        cur.fetchall.return_value = []                 # sin candidatas → familia nueva
        cur.fetchone.side_effect = [{"id": "fam-1"}]   # el insert gana
        is_new = _repo()._match_and_insert_failure(cur, org_id="o", run_id="r",
                                                   item=_item("sig-a"))
        assert is_new is True
        insert = next(s for s in _sqls(cur) if "insert into public.defect_families" in s)
        assert "on conflict (org_id, signature) where scope = 'org' do nothing" in insert
        assert "returning id" in insert

    def test_concurrent_insert_falls_back_to_existing_family(self):
        """Otro run de la misma org creó la familia entre la búsqueda y el insert:
        en vez de UniqueViolation (502 y run perdido) se suma a la existente."""
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.fetchone.side_effect = [
            None,                                          # on conflict do nothing
            {"id": "fam-otro"},                            # familia por firma
            {"occurrence_count": 1, "centroid": [0.1] * 384},  # for update
        ]
        is_new = _repo()._match_and_insert_failure(cur, org_id="o", run_id="r",
                                                   item=_item("sig-a"))
        assert is_new is False
        sqls = _sqls(cur)
        assert any("for update" in s for s in sqls)
        assert any("set occurrence_count = occurrence_count + 1" in s for s in sqls)
        failure_insert = cur.execute.call_args_list[-1]
        assert "insert into public.failures" in str(failure_insert.args[0])
        assert "fam-otro" in failure_insert.args[1]

    def test_ingest_locks_org_and_processes_failures_sorted_by_signature(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [{"ok": True}, {"id": "run-1"}]
        repo = _repo()
        seen = []

        def fake_match(_cur, *, org_id, run_id, item):
            seen.append(item.fingerprint)
            return False

        with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)), \
                patch.object(repo, "_match_and_insert_failure", side_effect=fake_match):
            repo.ingest_run(user_id="u", org_id="o", project="p", source="junit",
                            items=[_item("c"), _item("a"), _item("b")], run_uid="x")
        assert seen == ["a", "b", "c"]
        assert any("pg_advisory_xact_lock" in s for s in _sqls(cur))


# ---------------------------------------------------------------------------
# #5 — ingest_run persiste resultados por test (y el commit)
# ---------------------------------------------------------------------------

def test_ingest_run_persists_results_and_commit():
    cur = MagicMock()
    cur.fetchone.side_effect = [{"ok": True}, {"id": "run-1"}]
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
        _repo().ingest_run(user_id="u", org_id="o", project="p", source="junit", items=[],
                           commit_sha="abc1234", run_uid="x",
                           results=[{"test_name": "t", "status": "pass", "retried": False}])
    run_insert = next(c for c in cur.execute.call_args_list
                      if "insert into public.test_runs" in str(c.args[0]))
    assert "abc1234" in run_insert.args[1]
    rows = cur.executemany.call_args.args[1]
    assert list(rows) == [("run-1", "o", "t", "pass", False)]


# ---------------------------------------------------------------------------
# #18 — retención de snapshots DOM y triaje sin cargar todos los DOM
# ---------------------------------------------------------------------------

def test_ci_ingest_prunes_old_dom_snapshots_of_written_tests():
    cur = MagicMock()
    cur.fetchone.side_effect = [{"ok": True}, {"id": "run-1"}]
    snaps = [{"test_name": "t1", "kind": "last_green", "content": "<a/>"}]
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)), \
            patch("src.defects.repository.DOM_SNAPSHOTS_KEEP_PER_TEST", 2):
        _repo().ingest_ci_run(user_id="u", org_id="o", project="p", source="playwright",
                              run_uid="x", items=[], results=[], snapshots=snaps)
    prune = next(c for c in cur.execute.call_args_list
                 if "delete from public.dom_snapshots" in str(c.args[0]))
    sql = " ".join(str(prune.args[0]).split())
    assert "row_number() over (partition by test_name, kind" in sql
    assert "test_name = any(" in sql
    params = prune.args[1]
    assert params["org"] == "o" and params["project"] == "p"
    assert params["tests"] == ["t1"] and params["keep"] == 2


def test_triage_inputs_only_load_dom_of_failed_tests():
    cur = MagicMock()
    cur.fetchone.return_value = {"id": "r", "org_id": "o", "project": "p", "commit_sha": "s"}
    cur.fetchall.side_effect = [
        [{"failure_id": "f1", "test_name": "falla", "error_type": None, "message": "m",
          "trace": None, "fingerprint": "fp", "defect_family_id": None,
          "family_label": None}],
        [],  # retry_passed
        [],  # intermittent
        [],  # green DOM
        [],  # failure DOM
    ]
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
        _repo().get_triage_inputs(user_id="u", run_id="r")
    dom_calls = [c for c in cur.execute.call_args_list
                 if "from public.dom_snapshots" in str(c.args[0])]
    assert len(dom_calls) == 2
    for c in dom_calls:
        assert "test_name = any(" in str(c.args[0])
        assert ["falla"] in list(c.args[1])


# ---------------------------------------------------------------------------
# #19b — ¿un run deduplicado necesita relanzar el pipeline?
# ---------------------------------------------------------------------------

class TestRunNeedsPipeline:
    def _call(self, row):
        cur = MagicMock()
        cur.fetchone.return_value = row
        with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
            out = _repo().run_needs_pipeline(user_id="u", run_id="r")
        return out, cur

    def test_failures_without_verdicts_needs_pipeline(self):
        out, _ = self._call({"has_cert": True, "has_failures": True, "has_verdicts": False})
        assert out is True

    def test_missing_certificate_needs_pipeline(self):
        out, _ = self._call({"has_cert": False, "has_failures": False, "has_verdicts": False})
        assert out is True

    def test_complete_run_does_not(self):
        out, _ = self._call({"has_cert": True, "has_failures": True, "has_verdicts": True})
        assert out is False

    def test_not_member_or_missing_run_does_not(self):
        out, cur = self._call(None)
        assert out is False
        assert "public.memberships" in _sqls(cur)[-1]


def test_is_member():
    cur = MagicMock()
    cur.fetchone.return_value = {"ok": True}
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
        assert _repo().is_member(user_id="u", org_id="o") is True
    assert cur.execute.call_args.args[1] == ("o", "u")
