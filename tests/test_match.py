import pytest

from src.defects.match import FamilyCandidate, decide_match


def test_exact_fingerprint_match_wins():
    cands = [FamilyCandidate(family_id="f1", signature="abc", centroid=[0.0, 1.0])]
    res = decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=cands)
    assert res.family_id == "f1" and res.is_new is False and res.score == 1.0


def test_cosine_match_over_threshold():
    cands = [FamilyCandidate(family_id="f1", signature="zzz", centroid=[1.0, 0.0])]
    res = decide_match(fingerprint="abc", embedding=[0.99, 0.01], candidates=cands, threshold=0.85)
    assert res.family_id == "f1" and res.is_new is False and res.score >= 0.85


def test_new_family_when_below_threshold():
    cands = [FamilyCandidate(family_id="f1", signature="zzz", centroid=[1.0, 0.0])]
    res = decide_match(fingerprint="abc", embedding=[0.0, 1.0], candidates=cands, threshold=0.85)
    assert res.family_id is None and res.is_new is True


def test_new_family_when_no_candidates():
    res = decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=[])
    assert res.is_new is True and res.family_id is None


def test_decide_match_picks_best_cosine():
    cands = [
        FamilyCandidate(family_id="f1", signature="s1", centroid=[1.0, 0.0]),
        FamilyCandidate(family_id="f2", signature="s2", centroid=[0.0, 1.0]),
    ]
    res = decide_match(fingerprint="abc", embedding=[0.1, 0.99], candidates=cands, threshold=0.85)
    assert res.family_id == "f2"


def test_decide_match_mismatched_dims_raises():
    cands = [FamilyCandidate(family_id="f1", signature="zzz", centroid=[1.0, 0.0, 0.0])]
    with pytest.raises(ValueError):
        decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=cands)
