from src.jira.models import JiraBug, adf_to_text


def test_jirabug_defaults_url_empty():
    b = JiraBug(key="P-1", summary="s", description="d", issue_type="Bug", status="Open")
    assert b.url == ""


def test_adf_to_text_flattens_nested_doc():
    adf = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Login"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "timeout 30s"}]},
    ]}
    assert adf_to_text(adf) == "Login timeout 30s"


def test_adf_to_text_passthrough_and_none():
    assert adf_to_text("plain text") == "plain text"
    assert adf_to_text(None) == ""
