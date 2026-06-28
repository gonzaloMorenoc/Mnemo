"""
Tests for detect_gaps — deterministic gap detection (no LLM dependency).

Unit tests: mock _connect/_is_member so no DB needed.
Integration tests: marked @pytest.mark.integration.
"""
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — mirror graph/service test pattern exactly
# ---------------------------------------------------------------------------

def _make_conn_ctx(member: bool, fetchall_results: list = None, n_tests: int = 0):
    """
    Return (conn_ctx, conn, cur) configured for membership=member.

    fetchall_results: list of lists consumed sequentially by cur.fetchall().
      - Slot 0: defecto_sin_conocimiento rows
      - Slot 1: dominio_sin_leccion rows
      - Slot 2: riesgo_sin_mitigacion rows
      - Slot 3: coverage_rows (regla_sin_test cross-query), only consumed when n_tests>0

    n_tests: value returned by the count(test_assets) fetchone call.
      fetchone is called twice: once for membership ({"ok": member}),
      once for the test-count ({"n": n_tests}).
    """
    cur = MagicMock()
    cur.fetchone.side_effect = [{"ok": member}, {"n": n_tests}]

    if fetchall_results is not None:
        cur.fetchall.side_effect = list(fetchall_results)
    else:
        cur.fetchall.return_value = []

    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx

    conn_ctx = MagicMock()
    conn_ctx.__enter__ = MagicMock(return_value=conn)
    conn_ctx.__exit__ = MagicMock(return_value=False)

    return conn_ctx, conn, cur


ORG_ID = "aaaaaaaa-0000-0000-0000-000000000001"
USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"

# defect_family rows returned by first gap query
DEFECT_ROW_HIGH = {"id": "f1", "title": "NullPointer in login", "occurrence_count": 7}
DEFECT_ROW_MEDIA = {"id": "f2", "title": "Timeout in payment", "occurrence_count": 3}
DEFECT_ROW_LOW = {"id": "f3", "title": "Minor UI glitch", "occurrence_count": 1}

# domain knowledge rows for dominio_sin_leccion gap
DOMAIN_ROW_NO_LESSON = {"domain": "facturacion"}

# knowledge rows for riesgo_sin_mitigacion gap
RIESGO_ROW = {"id": "k1", "title": "Data leak risk", "kind": "riesgo", "domain": "seguridad"}


# ---------------------------------------------------------------------------
# Non-member → []
# ---------------------------------------------------------------------------

class TestDetectGapsNonMember:
    def test_returns_empty_when_not_member(self):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            result = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        assert result == []


# ---------------------------------------------------------------------------
# defecto_sin_conocimiento — severity by occurrence_count
# ---------------------------------------------------------------------------

class TestDefectoSinConocimiento:
    def _run_with(self, defect_rows):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[defect_rows, [], []],  # gap1 results, gap2, gap3
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value={"recommendation": "LLM rec"}):
                return detect_gaps(user_id=USER_ID, org_id=ORG_ID)

    def test_high_severity_when_occurrence_gte_5(self):
        gaps = self._run_with([DEFECT_ROW_HIGH])
        dsk = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"]
        assert len(dsk) == 1
        assert dsk[0]["severity"] == "alta"
        assert dsk[0]["title"] == DEFECT_ROW_HIGH["title"]

    def test_media_severity_when_occurrence_gte_2(self):
        gaps = self._run_with([DEFECT_ROW_MEDIA])
        dsk = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"]
        assert len(dsk) == 1
        assert dsk[0]["severity"] == "media"

    def test_baja_severity_when_occurrence_lt_2(self):
        gaps = self._run_with([DEFECT_ROW_LOW])
        dsk = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"]
        assert len(dsk) == 1
        assert dsk[0]["severity"] == "baja"

    def test_required_gap_fields_present(self):
        gaps = self._run_with([DEFECT_ROW_HIGH])
        gap = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"][0]
        for field in ("kind", "title", "severity", "affected", "recommendation"):
            assert field in gap, f"Missing field: {field}"

    def test_affected_is_list_of_strings(self):
        gaps = self._run_with([DEFECT_ROW_HIGH])
        gap = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"][0]
        assert isinstance(gap["affected"], list), "affected must be list[str]"
        assert gap["affected"] == ["f1"], f"Expected ['f1'], got {gap['affected']}"

    def test_llm_recommendation_used_when_available(self):
        gaps = self._run_with([DEFECT_ROW_HIGH])
        gap = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"][0]
        assert gap["recommendation"] == "LLM rec"


# ---------------------------------------------------------------------------
# dominio_sin_leccion
# ---------------------------------------------------------------------------

class TestDominioSinLeccion:
    def _run_with(self, domain_rows):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], domain_rows, []],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value={"recommendation": "LLM rec"}):
                return detect_gaps(user_id=USER_ID, org_id=ORG_ID)

    def test_gap_appears_for_domain_without_lesson(self):
        gaps = self._run_with([DOMAIN_ROW_NO_LESSON])
        dsl = [g for g in gaps if g["kind"] == "dominio_sin_leccion"]
        assert len(dsl) == 1
        assert dsl[0]["title"] == "facturacion"

    def test_severity_is_media_for_domain_gap(self):
        gaps = self._run_with([DOMAIN_ROW_NO_LESSON])
        dsl = [g for g in gaps if g["kind"] == "dominio_sin_leccion"]
        assert dsl[0]["severity"] == "media"

    def test_required_gap_fields_present(self):
        gaps = self._run_with([DOMAIN_ROW_NO_LESSON])
        gap = [g for g in gaps if g["kind"] == "dominio_sin_leccion"][0]
        for field in ("kind", "title", "severity", "affected", "recommendation"):
            assert field in gap, f"Missing field: {field}"

    def test_affected_is_list_of_strings(self):
        gaps = self._run_with([DOMAIN_ROW_NO_LESSON])
        gap = [g for g in gaps if g["kind"] == "dominio_sin_leccion"][0]
        assert isinstance(gap["affected"], list), "affected must be list[str]"
        assert gap["affected"] == ["facturacion"], f"Expected ['facturacion'], got {gap['affected']}"

    def test_no_domain_gaps_when_result_empty(self):
        gaps = self._run_with([])
        dsl = [g for g in gaps if g["kind"] == "dominio_sin_leccion"]
        assert dsl == []


# ---------------------------------------------------------------------------
# riesgo_sin_mitigacion
# ---------------------------------------------------------------------------

class TestRiesgoSinMitigacion:
    def _run_with(self, riesgo_rows):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], [], riesgo_rows],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value={"recommendation": "LLM rec"}):
                return detect_gaps(user_id=USER_ID, org_id=ORG_ID)

    def test_gap_appears_for_riesgo_without_mitigation(self):
        gaps = self._run_with([RIESGO_ROW])
        rsm = [g for g in gaps if g["kind"] == "riesgo_sin_mitigacion"]
        assert len(rsm) == 1
        assert rsm[0]["title"] == RIESGO_ROW["title"]

    def test_severity_is_alta_for_riesgo(self):
        gaps = self._run_with([RIESGO_ROW])
        rsm = [g for g in gaps if g["kind"] == "riesgo_sin_mitigacion"]
        assert rsm[0]["severity"] == "alta"

    def test_required_gap_fields_present(self):
        gaps = self._run_with([RIESGO_ROW])
        gap = [g for g in gaps if g["kind"] == "riesgo_sin_mitigacion"][0]
        for field in ("kind", "title", "severity", "affected", "recommendation"):
            assert field in gap, f"Missing field: {field}"

    def test_affected_is_list_of_strings(self):
        gaps = self._run_with([RIESGO_ROW])
        gap = [g for g in gaps if g["kind"] == "riesgo_sin_mitigacion"][0]
        assert isinstance(gap["affected"], list), "affected must be list[str]"
        assert gap["affected"] == ["seguridad"], f"Expected ['seguridad'], got {gap['affected']}"

    def test_no_riesgo_gaps_when_result_empty(self):
        gaps = self._run_with([])
        rsm = [g for g in gaps if g["kind"] == "riesgo_sin_mitigacion"]
        assert rsm == []


# ---------------------------------------------------------------------------
# LLM degradation — generate_structured → None → fixed recommendation (non-empty)
# ---------------------------------------------------------------------------

class TestLlmDegradation:
    def test_fixed_recommendation_when_llm_returns_none(self):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[DEFECT_ROW_HIGH], [], []],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value=None):
                gaps = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        dsk = [g for g in gaps if g["kind"] == "defecto_sin_conocimiento"]
        assert len(dsk) == 1
        rec = dsk[0]["recommendation"]
        assert rec  # must be non-empty
        assert isinstance(rec, str)

    def test_fixed_recommendation_for_dominio_sin_leccion(self):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], [DOMAIN_ROW_NO_LESSON], []],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value=None):
                gaps = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        dsl = [g for g in gaps if g["kind"] == "dominio_sin_leccion"]
        assert dsl[0]["recommendation"]

    def test_fixed_recommendation_for_riesgo_sin_mitigacion(self):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], [], [RIESGO_ROW]],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value=None):
                gaps = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        rsm = [g for g in gaps if g["kind"] == "riesgo_sin_mitigacion"]
        assert rsm[0]["recommendation"]


# ---------------------------------------------------------------------------
# Detection is independent of the LLM — gaps appear even if LLM raises
# ---------------------------------------------------------------------------

class TestDetectionNeverDependsOnLlm:
    def test_gaps_appear_when_llm_raises(self):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[DEFECT_ROW_HIGH], [DOMAIN_ROW_NO_LESSON], [RIESGO_ROW]],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", side_effect=RuntimeError("LLM down")):
                gaps = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        kinds = {g["kind"] for g in gaps}
        assert "defecto_sin_conocimiento" in kinds
        assert "dominio_sin_leccion" in kinds
        assert "riesgo_sin_mitigacion" in kinds

    def test_recommendations_non_empty_when_llm_raises(self):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[DEFECT_ROW_HIGH], [], []],
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", side_effect=RuntimeError("LLM down")):
                gaps = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        for g in gaps:
            assert g["recommendation"], f"Empty recommendation in {g}"

    def test_detect_gaps_never_raises(self):
        """detect_gaps must catch all exceptions internally."""
        from src.graph.gaps import detect_gaps
        # Make _connect itself raise
        with patch("src.graph.gaps.psycopg.connect", side_effect=Exception("DB down")):
            result = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        assert result == []


# ---------------------------------------------------------------------------
# regla_sin_test — coverage gap via cosine similarity cross-query
# ---------------------------------------------------------------------------

# qa_knowledge rows for coverage cross-query
REGLA_ROW_COVERED = {
    "id": "k10",
    "title": "Login must require 2FA",
    "kind": "regla_negocio",
    "best_dist": 0.30,  # < threshold → covered, NO gap
}
REGLA_ROW_UNCOVERED = {
    "id": "k11",
    "title": "Payment timeout must be ≤ 5s",
    "kind": "regla_negocio",
    "best_dist": 0.80,  # > threshold → gap, severity media
}
RIESGO_ROW_FAR = {
    "id": "k12",
    "title": "Data leak via API",
    "kind": "riesgo",
    "best_dist": 0.90,  # > threshold → gap, severity alta
}
REGLA_ROW_NULL_DIST = {
    "id": "k13",
    "title": "Billing rule with no test embedding",
    "kind": "regla_negocio",
    "best_dist": None,  # None treated as > threshold → gap
}


class TestReglaSinTest:
    """Coverage gap: qa_knowledge × test_assets via cosine similarity."""

    def _run(self, coverage_rows, n_tests=5):
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], [], [], coverage_rows],
            n_tests=n_tests,
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch(
                "src.graph.gaps.generate_structured",
                return_value={"recommendation": "LLM rec coverage"},
            ):
                return detect_gaps(user_id=USER_ID, org_id=ORG_ID)

    def test_near_test_no_gap(self):
        """best_dist < threshold → knowledge is covered → NO regla_sin_test gap."""
        gaps = self._run([REGLA_ROW_COVERED])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert rst == [], f"Expected no regla_sin_test, got {rst}"

    def test_far_regla_negocio_produces_gap_severity_media(self):
        """best_dist > threshold + kind=regla_negocio → gap with severity=media."""
        gaps = self._run([REGLA_ROW_UNCOVERED])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert len(rst) == 1
        assert rst[0]["severity"] == "media"
        assert rst[0]["title"] == REGLA_ROW_UNCOVERED["title"]

    def test_far_riesgo_produces_gap_severity_alta(self):
        """best_dist > threshold + kind=riesgo → gap with severity=alta."""
        gaps = self._run([RIESGO_ROW_FAR])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert len(rst) == 1
        assert rst[0]["severity"] == "alta"
        assert rst[0]["title"] == RIESGO_ROW_FAR["title"]

    def test_null_best_dist_treated_as_uncovered(self):
        """best_dist=None → no matching test → gap produced."""
        gaps = self._run([REGLA_ROW_NULL_DIST])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert len(rst) == 1

    def test_affected_is_knowledge_id(self):
        """affected list must contain the qa_knowledge id."""
        gaps = self._run([REGLA_ROW_UNCOVERED])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert rst[0]["affected"] == [REGLA_ROW_UNCOVERED["id"]]

    def test_llm_recommendation_used_when_available(self):
        gaps = self._run([REGLA_ROW_UNCOVERED])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert rst[0]["recommendation"] == "LLM rec coverage"

    def test_fallback_recommendation_when_llm_returns_none(self):
        """generate_structured → None → falls back to _FALLBACK_REC["regla_sin_test"]."""
        from src.graph.gaps import _FALLBACK_REC, detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], [], [], [REGLA_ROW_UNCOVERED]],
            n_tests=5,
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            with patch("src.graph.gaps.generate_structured", return_value=None):
                gaps = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert len(rst) == 1
        assert rst[0]["recommendation"] == _FALLBACK_REC["regla_sin_test"]

    def test_required_gap_fields_present(self):
        gaps = self._run([REGLA_ROW_UNCOVERED])
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        for field in ("kind", "title", "severity", "affected", "recommendation"):
            assert field in rst[0], f"Missing field: {field}"


# ---------------------------------------------------------------------------
# repo_no_indexado — when count(test_assets) == 0
# ---------------------------------------------------------------------------

class TestRepoNoIndexado:
    """When no test_assets exist for the org, emit exactly one repo_no_indexado gap."""

    def _run(self, knowledge_rows=None):
        """n_tests=0 → branch that emits repo_no_indexado instead of cross-query."""
        from src.graph.gaps import detect_gaps
        # When n_tests==0, coverage cross-query is NEVER called → only 3 fetchall slots
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[[], [], []],
            n_tests=0,
        )
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            return detect_gaps(user_id=USER_ID, org_id=ORG_ID)

    def test_exactly_one_repo_no_indexado_gap(self):
        gaps = self._run()
        rni = [g for g in gaps if g["kind"] == "repo_no_indexado"]
        assert len(rni) == 1

    def test_no_regla_sin_test_when_no_tests_indexed(self):
        gaps = self._run()
        rst = [g for g in gaps if g["kind"] == "regla_sin_test"]
        assert rst == [], f"Expected no regla_sin_test, got {rst}"

    def test_repo_no_indexado_severity_is_media(self):
        gaps = self._run()
        rni = [g for g in gaps if g["kind"] == "repo_no_indexado"]
        assert rni[0]["severity"] == "media"

    def test_repo_no_indexado_affected_is_empty_list(self):
        gaps = self._run()
        rni = [g for g in gaps if g["kind"] == "repo_no_indexado"]
        assert rni[0]["affected"] == []

    def test_repo_no_indexado_has_non_empty_recommendation(self):
        gaps = self._run()
        rni = [g for g in gaps if g["kind"] == "repo_no_indexado"]
        assert rni[0]["recommendation"]

    def test_required_gap_fields_present(self):
        gaps = self._run()
        rni = [g for g in gaps if g["kind"] == "repo_no_indexado"]
        for field in ("kind", "title", "severity", "affected", "recommendation"):
            assert field in rni[0], f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Coverage gap non-member → [] (regression guard)
# ---------------------------------------------------------------------------

class TestCoverageGapNonMember:
    def test_returns_empty_for_non_member_even_with_tests(self):
        """Non-member org returns [] regardless of test_assets count."""
        from src.graph.gaps import detect_gaps
        conn_ctx, conn, cur = _make_conn_ctx(member=False, n_tests=10)
        with patch("src.graph.gaps.psycopg.connect", return_value=conn_ctx):
            result = detect_gaps(user_id=USER_ID, org_id=ORG_ID)
        assert result == []
