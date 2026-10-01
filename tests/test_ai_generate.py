from src.ai.generate import generate_structured


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _Boom:
    def complete(self, prompt): raise RuntimeError("llm down")


def test_parses_valid_json_and_fills_defaults():
    prov = _Provider('prefacio {"root_cause": "x", "confidence": 0.9} epilogo')
    out = generate_structured(prompt="p", context=[{"id": "e1", "content": "c"}],
                              schema={"root_cause": "", "confidence": 0.0}, provider=prov)
    assert out["root_cause"] == "x" and out["confidence"] == 0.9


def test_degrades_to_fallback_on_provider_error():
    out = generate_structured(prompt="p", context=[], schema={"root_cause": "", "confidence": 0.0},
                              provider=_Boom())
    assert out == {"root_cause": "", "confidence": 0.0}


def test_degrades_to_none_when_requested():
    assert generate_structured(prompt="p", context=[], schema={"x": 0.0},
                               provider=_Boom(), on_failure="none") is None


def test_garbage_output_degrades():
    out = generate_structured(prompt="p", context=[], schema={"x": 1},
                              provider=_Provider("no json aquí"), on_failure="none")
    assert out is None


class _Captura:
    def __init__(self): self.prompt = None
    def complete(self, prompt):
        self.prompt = prompt
        return '{"answer": "ok", "citations": []}'


def test_prompt_pide_json_con_las_claves_del_esquema():
    # Sin pedirlo, modelos como gpt-oss responden en prosa y la respuesta se tira:
    # el formato lo exige generate_structured, no cada prompt por su cuenta.
    prov = _Captura()
    generate_structured(prompt="p", context=[], schema={"answer": "", "citations": []},
                        provider=prov, on_failure="none")
    instruccion = prov.prompt.split("Context snippets:")[-1]
    assert "JSON" in instruccion and '"answer"' in instruccion and '"citations"' in instruccion
