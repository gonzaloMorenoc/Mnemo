from src.assurance.verdict import build_verdict


def _fam(fid, title, occ, run_count):
    return {"id": fid, "title": title, "occurrence_count": occ, "run_count": run_count}


def test_verdict_counts_and_risk_attention_when_novel():
    v = build_verdict(run_summary={"ingested": 3, "known": 1, "novel": 2},
                      run_families=[_fam("f1", "Timeout", 5, 1)])
    assert v["ingested"] == 3 and v["known"] == 1 and v["novel"] == 2
    assert v["risk"] == "atencion"


def test_verdict_risk_ok_when_no_novel():
    v = build_verdict(run_summary={"ingested": 2, "known": 2, "novel": 0}, run_families=[])
    assert v["risk"] == "ok"


def test_verdict_top_families_sorted_and_recurring_flag():
    fams = [_fam("a", "A", 2, 2), _fam("b", "B", 9, 1), _fam("c", "C", 1, 1)]
    v = build_verdict(run_summary={"ingested": 3, "known": 1, "novel": 2}, run_families=fams)
    assert [f["id"] for f in v["top_families"]] == ["b", "a", "c"]
    by_id = {f["id"]: f for f in v["top_families"]}
    assert by_id["b"]["recurring"] is True
    assert by_id["a"]["recurring"] is False


def test_verdict_top_families_capped_at_5():
    fams = [_fam(str(i), str(i), 10 - i, 1) for i in range(8)]
    v = build_verdict(run_summary={"ingested": 8, "known": 0, "novel": 8}, run_families=fams)
    assert len(v["top_families"]) == 5
