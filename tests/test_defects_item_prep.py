"""Preparación de un fallo para la ingesta (auditoría 23-nov, #3).

La huella sale del texto CRUDO; lo almacenado y lo embebido es el texto saneado.
Un mensaje vacío o genérico no se embebe como cadena vacía y no se fusiona por
similitud: manda la identidad del test.
"""
from src.defects.fingerprint import fingerprint
from src.defects.item_prep import build_ingest_item, embedding_source
from src.defects.match import FamilyCandidate, decide_match
from src.ingest.models import FailureRecord


class RecordingEmbedder:
    def __init__(self):
        self.texts = []

    def embed(self, text):
        self.texts.append(text)
        return [1.0, 0.0]


def _rec(msg, trace=None, test_name="Cart adds item"):
    return FailureRecord(test_name=test_name, error_type=None, message=msg, trace=trace,
                         project="p", source="junit")


def test_fingerprint_is_from_raw_and_stored_text_is_sanitized():
    rec = _rec("Timeout calling https://api.example.com/checkout from 10.0.0.1",
               "at /home/runner/app/tests/cart.spec.ts:4:2")
    emb = RecordingEmbedder()
    item = build_ingest_item(rec, emb)
    assert item.fingerprint == fingerprint(rec)
    assert "10.0.0.1" not in item.rec.message and "api.example.com" not in item.rec.message
    assert "/home/runner" not in (item.rec.trace or "")
    assert "10.0.0.1" not in emb.texts[0]
    assert item.allow_similarity is False  # el saneador redactó parte del mensaje


def test_clean_informative_message_allows_similarity():
    item = build_ingest_item(_rec("Timeout waiting for selector #pay"), RecordingEmbedder())
    assert item.allow_similarity is True


def test_empty_message_does_not_embed_empty_string_and_disables_similarity():
    emb = RecordingEmbedder()
    item = build_ingest_item(_rec("", None), emb)
    assert emb.texts[0].strip() != ""
    assert "Cart adds item" in emb.texts[0]
    assert item.allow_similarity is False


def test_generic_message_uses_trace_line_and_test_identity():
    rec = _rec("Failed", "    login_test.go:12: expected 200, got 500", test_name="pkg/a.TestLogin")
    text = embedding_source(rec)
    assert "expected 200, got 500" in text and "TestLogin" in text


def test_informative_message_embeds_error_type_and_message():
    rec = FailureRecord(test_name="t", error_type="TimeoutError", message="waiting for #pay",
                        trace=None, project="p", source="junit")
    assert embedding_source(rec) == "TimeoutError waiting for #pay"


def test_decide_match_skips_similarity_when_not_allowed():
    cands = [FamilyCandidate(family_id="f1", signature="zzz", centroid=[1.0, 0.0])]
    res = decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=cands,
                       allow_similarity=False)
    assert res.is_new is True and res.family_id is None


def test_decide_match_exact_signature_still_wins_without_similarity():
    cands = [FamilyCandidate(family_id="f1", signature="abc", centroid=[0.0, 1.0])]
    res = decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=cands,
                       allow_similarity=False)
    assert res.family_id == "f1" and res.is_new is False


def test_messages_that_only_differ_in_redacted_urls_do_not_merge_by_similarity():
    """Escenario san_check de la auditoría: tras sanear, ambos mensajes son iguales."""
    a = _rec("Expected: https://shop.example.com/checkout Received: https://shop.example.com/login",
             test_name="checkout flow")
    b = _rec("Expected: https://shop.example.com/cart Received: https://shop.example.com/500",
             test_name="cart flow")
    emb = RecordingEmbedder()
    ia, ib = build_ingest_item(a, emb), build_ingest_item(b, emb)
    assert ia.fingerprint != ib.fingerprint
    assert ib.allow_similarity is False
    cands = [FamilyCandidate(family_id="fa", signature=ia.fingerprint, centroid=list(ia.embedding))]
    res = decide_match(fingerprint=ib.fingerprint, embedding=ib.embedding, candidates=cands,
                       allow_similarity=ib.allow_similarity)
    assert res.is_new is True
