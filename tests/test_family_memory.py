"""FamilyMemory y su presentación: check run, log del CI y bloque de la respuesta."""
from src.memory.family_memory import (MAX_FAMILIES, FamilyMemory, Lesson, clip, memory_payload,
                                      render_family_markdown, render_markdown, render_text)

APP = "https://mnemo.example"


def _mem(fid="f1", **kw):
    base = dict(family_id=fid, title="TimeoutError en pago", label="infra",
                reason="El sandbox del PSP se cae los lunes de 8 a 9", reason_by="María",
                reason_at="2026-10-02T08:00:00+00:00", runs=4, projects=("checkout",))
    return FamilyMemory(**{**base, **kw})


def test_sin_etiqueta_razon_ni_lecciones_no_hay_memoria():
    assert not FamilyMemory(family_id="f", title="x", label="unknown").has_memory
    assert not FamilyMemory(family_id="f", title="x").has_memory
    assert FamilyMemory(family_id="f", title="x", label="flaky").has_memory
    assert FamilyMemory(family_id="f", title="x",
                        lessons=(Lesson("k", "leccion", "t", ""),)).has_memory


def test_el_check_run_cita_la_razon_con_autor_fecha_y_leccion():
    mem = _mem(lessons=(Lesson("k1", "leccion", "Mirar X-RateLimit", "Si está a cero, espaciar"),))
    md = render_markdown([mem], app_url=APP)
    assert md.startswith("### Lo que Mnemo recuerda")
    assert "entorno / infraestructura" in md
    assert "> El sandbox del PSP se cae los lunes de 8 a 9" in md
    assert "María, 2026-10-02" in md
    assert "Lección: Mirar X-RateLimit: Si está a cero, espaciar" in md
    assert f"{APP}/app/defects?family=f1" in md


def test_sin_memoria_no_hay_seccion():
    assert render_markdown([FamilyMemory(family_id="f", title="x")]) == ""
    assert render_text([]) == ""
    assert memory_payload([FamilyMemory(family_id="f", title="x")]) is None


def test_autor_que_ya_no_esta_en_la_org():
    md = render_family_markdown(_mem(reason_by_active=False))
    assert "ya no está en la organización" in md


def test_razon_sin_nombre_visible():
    assert "alguien del equipo" in render_family_markdown(_mem(reason_by=None))


def test_neutraliza_menciones_y_html():
    md = render_family_markdown(_mem(reason="avisar a @pagos-team <script>x</script>"))
    assert "@pagos-team" not in md and "@​pagos-team" in md
    assert "<script>" not in md


def test_tope_de_familias_y_aviso_del_resto():
    mems = [_mem(fid=f"f{i}") for i in range(MAX_FAMILIES + 3)]
    md = render_markdown(mems)
    assert md.count("> El sandbox") == MAX_FAMILIES
    assert "…y 3 familias más" in md


def test_tope_de_caracteres():
    largo = "palabra " * 60
    mems = [_mem(fid=f"f{i}", reason=largo) for i in range(5)]
    md = render_markdown(mems, max_chars=900)
    assert len(md) <= 1000
    assert "más con memoria en Mnemo" in md


def test_sin_url_de_la_app_no_hay_enlace():
    assert "Ver en Mnemo" not in render_markdown([_mem()], app_url="")


def test_texto_plano_para_el_log_del_ci():
    text = render_text([_mem(lessons=(Lesson("k", "leccion", "Espaciar la suite", ""),))])
    assert text.splitlines()[0] == "Lo que Mnemo recuerda de los fallos de este run:"
    assert "[entorno / infraestructura]" in text
    assert "Por qué: El sandbox del PSP" in text and "Lección: Espaciar la suite" in text
    assert "**" not in text and ">" not in text


def test_payload_solo_con_las_familias_con_memoria():
    out = memory_payload([_mem(), FamilyMemory(family_id="f2", title="sin nada")])
    assert out["remembered"] == 1
    assert [f["family_id"] for f in out["families"]] == ["f1"]
    assert out["families"][0]["label_text"] == "entorno / infraestructura"
    assert out["text"]


def test_clip_corta_en_palabra():
    assert clip("uno dos tres cuatro", 10) == "uno dos…"
    assert clip("  muchos   espacios ", 50) == "muchos espacios"
    assert clip(None, 5) == ""


# ── Revisión: lo escrito por personas sale inerte a GitHub y al CI ──
from src.memory.family_memory import memory_summary_payload  # noqa: E402


def test_enlaces_imagenes_encabezados_y_referencias_quedan_inertes():
    md = render_family_markdown(_mem(reason="ver [aquí](https://evil) ![](https://t.co/px) #12 org/r#3"))
    assert "](" not in md.replace("\\](", "") and "![" not in md.replace("\\!\\[", "")
    assert "\\[aquí\\]\\(https://evil\\)" in md and "\\#12" in md


def test_controles_y_bidi_desaparecen():
    md = render_family_markdown(_mem(reason="a\x1b[2Jb ‮oculto"))
    text = render_text([_mem(reason="a\x1b[2Jb ‮oculto")])
    for out in (md, text):
        assert "\x1b" not in out and "‮" not in out


def test_proyecto_y_autor_no_rompen_la_cabecera():
    mem = _mem(projects=("web", "x\n\n# Titular\n![](https://t)"), reason_by="Ana\n# h")
    md = render_family_markdown(mem)
    assert "\n#" not in md and "![" not in md
    assert md.splitlines()[0].startswith("**TimeoutError")


def test_resumen_para_token_sin_contenido_escrito():
    mem = _mem(lessons=(Lesson("k", "leccion", "Secreto de oficio", "detalle"),))
    out = memory_summary_payload([mem, FamilyMemory("f2", "nada")], app_url=APP)
    assert out["remembered"] == 1 and out["detail"] is False
    assert out["families"] == [{"family_id": "f1", "title": "TimeoutError en pago",
                                "label_text": "entorno / infraestructura",
                                "url": f"{APP}/app/defects?family=f1"}]
    assert "sandbox" not in str(out) and "Secreto" not in str(out) and "María" not in str(out)
    assert f"{APP}/app/defects" in out["text"]
    assert memory_summary_payload([FamilyMemory("f", "x")]) is None


def test_el_email_solo_sale_hacia_la_app():
    mem = _mem(reason_by=None, reason_by_email="maria@empresa.com")
    assert "reason_by_email" not in mem.to_dict()
    assert mem.to_dict(include_private=True)["reason_by_email"] == "maria@empresa.com"
    assert "maria@empresa.com" not in render_markdown([mem]) + render_text([mem])
    assert "maria@empresa.com" not in str(memory_payload([mem]))
