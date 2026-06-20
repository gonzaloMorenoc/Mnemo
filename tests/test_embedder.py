from src.defects.embedder import Embedder, LocalEmbedder


def test_local_embedder_is_embedder_protocol():
    emb = LocalEmbedder()
    assert isinstance(emb, Embedder)
    assert emb._hf is None  # no cargado hasta el primer embed


def test_fake_embedder_satisfies_protocol():
    class Fake:
        def embed(self, text: str):
            return [1.0, 2.0]

    def use(e: Embedder):
        return e.embed("x")

    assert use(Fake()) == [1.0, 2.0]
