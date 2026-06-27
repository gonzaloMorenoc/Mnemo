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

def _make_conn_ctx(member: bool, fetchall_results: list = None):
    """
    Return (conn_ctx, conn, cur) configured for membership=member.

    fetchall_results: list of lists consumed sequentially by cur.fetchall().
    The first call after the membership fetchone() gets fetchall_results[0], etc.
    """
    cur = MagicMock()
    cur.fetchone.return_value = {"ok": member}

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
