from unittest.mock import patch

from src.onboarding.agent import summarize_domain, learning_path

# ---------------------------------------------------------------------------
# Fake knowledge_service
# ---------------------------------------------------------------------------

_SOURCES = [
    {"id": "knowledge:k1", "type": "knowledge", "content": "El flujo de login usa OAuth2."},
    {"id": "defect:d1",    "type": "defect",    "content": "Timeout en sesión SSO con ADFS."},
]


class _FakeKS:
    def search_unified(self, *, user_id, org_id, query, k):
        return _SOURCES


_SUMMARY_RESPONSE = {
    "rules": ["Solo usuarios activos pueden iniciar sesión"],
    "systems": ["auth-service", "oauth2-provider"],
    "existing_tests": ["test_login_happy_path", "test_session_expiry"],
    "historical_bugs": ["Timeout con ADFS"],
    "risks": ["SSO puede fallar en redes restringidas"],
    "citations": ["knowledge:k1", "defect:d1"],
}

_PATH_RESPONSE = {
    "days": [
        {"day": 1, "items": ["Leer el flujo feliz de login", "Revisar OAuth2 docs"]},
        {"day": 2, "items": ["Explorar casos negativos", "Revisar bugs históricos de SSO"]},
        {"day": 3, "items": ["Automatizar test_login_happy_path"]},
    ],
    "citations": ["knowledge:k1", "defect:d1"],
}


# ---------------------------------------------------------------------------
# Tests — summarize_domain
# ---------------------------------------------------------------------------

def test_summarize_domain_returns_all_fields_with_citations():
    """generate_structured devuelve el resumen → todas las claves + citations."""
    with patch("src.onboarding.agent.generate_structured", return_value=_SUMMARY_RESPONSE) as mock_gs:
        result = summarize_domain(
            knowledge_service=_FakeKS(),
            user_id="u1",
            org_id="o1",
            topic="autenticación",
        )

    assert isinstance(result, dict)
    assert isinstance(result["rules"], list)
    assert isinstance(result["systems"], list)
    assert isinstance(result["existing_tests"], list)
    assert isinstance(result["historical_bugs"], list)
    assert isinstance(result["risks"], list)
    assert isinstance(result["citations"], list)
    assert "knowledge:k1" in result["citations"]
    assert "defect:d1" in result["citations"]
    mock_gs.assert_called_once()


def test_summarize_domain_degrades_when_llm_returns_none():
    """generate_structured → None → fallback: todas las claves, sources citadas, nunca lanza."""
    with patch("src.onboarding.agent.generate_structured", return_value=None):
        result = summarize_domain(
            knowledge_service=_FakeKS(),
            user_id="u1",
            org_id="o1",
            topic="autenticación",
        )

    assert isinstance(result, dict)
    assert isinstance(result["rules"], list)
    assert isinstance(result["systems"], list)
    assert isinstance(result["existing_tests"], list)
    assert isinstance(result["historical_bugs"], list)
    assert isinstance(result["risks"], list)
    assert isinstance(result["citations"], list)
    assert "knowledge:k1" in result["citations"]
    assert "defect:d1" in result["citations"]


def test_summarize_domain_normalizes_bad_types():
    """Si el LLM devuelve tipos incorrectos, se normalizan a listas vacías."""
    bad_response = {**_SUMMARY_RESPONSE, "rules": "not a list", "citations": 42}
    with patch("src.onboarding.agent.generate_structured", return_value=bad_response):
        result = summarize_domain(
            knowledge_service=_FakeKS(),
            user_id="u1",
            org_id="o1",
            topic="autenticación",
        )

    assert isinstance(result["rules"], list)
    assert isinstance(result["citations"], list)


# ---------------------------------------------------------------------------
# Tests — learning_path
# ---------------------------------------------------------------------------

def test_learning_path_returns_days_with_citations():
    """generate_structured devuelve la ruta → days + citations con source ids."""
    with patch("src.onboarding.agent.generate_structured", return_value=_PATH_RESPONSE) as mock_gs:
        result = learning_path(
            knowledge_service=_FakeKS(),
            user_id="u1",
            org_id="o1",
            topic="autenticación",
        )

    assert isinstance(result, dict)
    assert isinstance(result["days"], list)
    assert len(result["days"]) == 3
    assert isinstance(result["citations"], list)
    assert "knowledge:k1" in result["citations"]
    assert "defect:d1" in result["citations"]
    mock_gs.assert_called_once()


def test_learning_path_degrades_when_llm_returns_none():
    """generate_structured → None → fallback: days tiene un item, sources citadas, nunca lanza."""
    with patch("src.onboarding.agent.generate_structured", return_value=None):
        result = learning_path(
            knowledge_service=_FakeKS(),
            user_id="u1",
            org_id="o1",
            topic="autenticación",
        )

    assert isinstance(result, dict)
    assert isinstance(result["days"], list)
    assert len(result["days"]) >= 1
    assert result["days"][0]["items"]
    assert isinstance(result["citations"], list)
    assert "knowledge:k1" in result["citations"]
    assert "defect:d1" in result["citations"]


def test_learning_path_normalizes_bad_types():
    """Si el LLM devuelve tipos incorrectos en days o citations, se normalizan."""
    bad_response = {"days": "not a list", "citations": None}
    with patch("src.onboarding.agent.generate_structured", return_value=bad_response):
        result = learning_path(
            knowledge_service=_FakeKS(),
            user_id="u1",
            org_id="o1",
            topic="autenticación",
        )

    assert isinstance(result["days"], list)
    assert isinstance(result["citations"], list)


def test_gather_passes_topic_as_query():
    """_gather pasa el topic como query a search_unified."""
    calls = []

    class _TrackingKS:
        def search_unified(self, *, user_id, org_id, query, k):
            calls.append({"query": query, "k": k})
            return _SOURCES

    with patch("src.onboarding.agent.generate_structured", return_value=_SUMMARY_RESPONSE):
        summarize_domain(
            knowledge_service=_TrackingKS(),
            user_id="u1",
            org_id="o1",
            topic="pagos con tarjeta",
        )

    assert len(calls) == 1
    assert calls[0]["query"] == "pagos con tarjeta"
    assert calls[0]["k"] == 8
