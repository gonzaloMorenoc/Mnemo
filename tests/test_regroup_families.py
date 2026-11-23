"""Plan del re-agrupado de familias con la huella v2 (scripts/regroup_families.py).
Solo la parte pura: el script no se ejecuta en los tests ni contra ninguna BD."""
from scripts.regroup_families import plan_family, stored_fingerprint


def _f(i, test_name, message="Failed", trace=None):
    return {"id": i, "test_name": test_name, "error_type": None, "message": message,
            "trace": trace, "file": None, "source": "junit"}


def test_family_merged_by_generic_message_is_split_by_test():
    fails = [_f(1, "pkg.TestLogin"), _f(2, "pkg.TestLogin"), _f(3, "pkg.TestPayment")]
    keep_fp, moves = plan_family(fails)
    assert keep_fp == stored_fingerprint(fails[0])
    assert moves == [(stored_fingerprint(fails[2]), [3])]


def test_homogeneous_family_is_not_split():
    fails = [_f(1, "pkg.TestLogin", "Timeout 30s"), _f(2, "pkg.TestLogin", "Timeout 45s")]
    _, moves = plan_family(fails)
    assert moves == []


def test_tie_is_deterministic():
    a, b = [_f(1, "A")], [_f(2, "B")]
    assert plan_family(a + b) == plan_family(b + a)
