# -*- coding: utf-8 -*-
"""Diagramas C4 de Mnemo (Nivel 1 Contexto y Nivel 2 Contenedores) en SVG, notación C4 estándar."""
from html import escape

# ---- Paleta C4 canónica ----
PERSON = ("#08427b", "#052e56")
SYSTEM = ("#1168bd", "#0b4884")   # sistema en alcance
CONT   = ("#438dd5", "#2e6295")   # contenedor
DB     = ("#438dd5", "#2e6295")
EXT    = ("#8a8a8a", "#635f5f")   # sistema/persona externa
REL    = "#6b6b6b"

def esc(s): return escape(s)

class SVG:
    def __init__(self): self.p = []
    def add(self, s): self.p.append(s)
    def wrap(self, W, H):
        c = max(W, H)
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{c*2}" height="{c*2}" '
                f'viewBox="0 0 {W} {c}">')
        defs = ('<defs><marker id="arr" markerWidth="10" markerHeight="10" refX="8" refY="3" '
                'orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="%s"/></marker>'
                '<style>text{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif}</style></defs>' % REL)
        bg = f'<rect x="0" y="0" width="{W}" height="{c}" fill="#ffffff"/>'
        return head + defs + bg + "".join(self.p) + "</svg>"

def txt(sv, x, y, s, size, fill, weight="400", anchor="middle", italic=False, family=None):
    fs = f' font-style="italic"' if italic else ""
    ff = f' font-family="ui-monospace,Menlo,monospace"' if family == "mono" else ""
    sv.add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
           f'text-anchor="{anchor}"{fs}{ff}>{esc(s)}</text>')

def wrap_lines(s, n):
    out, line = [], ""
    for w in s.split():
        if len(line) + len(w) + 1 > n:
            out.append(line); line = w
        else:
            line = (line + " " + w).strip()
    if line: out.append(line)
    return out

def box(sv, x, y, w, h, name, typ, desc, kind="system", shape="rect"):
    fill, stroke = {"person": PERSON, "system": SYSTEM, "cont": CONT, "ext": EXT, "db": DB}[kind]
    if shape == "person":
        # cabeza + cuerpo redondeado
        sv.add(f'<circle cx="{x+w/2}" cy="{y+20}" r="15" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        sv.add(f'<rect x="{x}" y="{y+38}" width="{w}" height="{h-38}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        cy = y + 58
        txt(sv, x+w/2, cy, name, 15, "#ffffff", "700"); cy += 17
        txt(sv, x+w/2, cy, typ, 11, "#cfe0f3", italic=True); cy += 16
        for ln in wrap_lines(desc, 30): txt(sv, x+w/2, cy, ln, 10.5, "#dbe8f6"); cy += 13
        return
    if shape == "cyl":
        rx, ry = w/2, 14
        sv.add(f'<path d="M{x},{y+ry} a{rx},{ry} 0 0 0 {w},0 v{h-2*ry} a{rx},{ry} 0 0 1 -{w},0 Z" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        sv.add(f'<path d="M{x},{y+ry} a{rx},{ry} 0 0 1 {w},0" fill="none" stroke="{stroke}" stroke-width="1.5"/>')
        cy = y + 42
    else:
        sv.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        cy = y + 30
    txt(sv, x+w/2, cy, name, 15.5, "#ffffff", "700"); cy += 18
    txt(sv, x+w/2, cy, typ, 11, "#d6e6f5", italic=True); cy += 16
    for ln in wrap_lines(desc, 34): txt(sv, x+w/2, cy, ln, 10.5, "#e3eef9"); cy += 13.5

def anchor_pt(b, side):
    x, y, w, h = b
    return {"t": (x+w/2, y), "b": (x+w/2, y+h), "l": (x, y+h/2), "r": (x+w, y+h/2),
            "tl": (x+w*0.25, y), "tr": (x+w*0.75, y), "bl": (x+w*0.25, y+h), "br": (x+w*0.75, y+h)}[side]

def rel(sv, b1, s1, b2, s2, label, tech=None, lx=None, ly=None):
    x1, y1 = anchor_pt(b1, s1); x2, y2 = anchor_pt(b2, s2)
    sv.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{REL}" stroke-width="1.6" '
           f'stroke-dasharray="1 0" marker-end="url(#arr)"/>')
    mx = lx if lx is not None else (x1+x2)/2
    my = ly if ly is not None else (y1+y2)/2
    lines = wrap_lines(label, 26)
    tw = max(len(l) for l in lines) * 6.0 + 14
    th = len(lines)*13 + (14 if tech else 4)
    sv.add(f'<rect x="{mx-tw/2}" y="{my-11}" width="{tw}" height="{th}" rx="4" fill="#ffffff" opacity="0.92"/>')
    yy = my
    for l in lines:
        txt(sv, mx, yy, l, 10.5, "#3a3a3a", "500"); yy += 13
    if tech: txt(sv, mx, yy, tech, 9.5, "#7a7a7a", italic=True, family="mono")

def legend(sv, x, y):
    items = [("Persona", PERSON[0]), ("Sistema (en alcance)", SYSTEM[0]),
             ("Contenedor", CONT[0]), ("Sistema externo", EXT[0])]
    txt(sv, x, y, "Leyenda", 12, "#333", "700", "start")
    cx = x
    for lbl, col in items:
        sv.add(f'<rect x="{cx}" y="{y+10}" width="16" height="12" rx="3" fill="{col}"/>')
        txt(sv, cx+22, y+20, lbl, 11, "#444", "500", "start")
        cx += 34 + len(lbl)*6.6

def title(sv, W, t, sub):
    txt(sv, W/2, 46, t, 26, "#0f172a", "700")
    txt(sv, W/2, 72, sub, 13.5, "#5b6b82", "400")

# ============================ NIVEL 1 — CONTEXTO ============================
def context():
    sv = SVG(); W, H = 1500, 1080
    title(sv, W, "Mnemo — Diagrama de Contexto (C4 · Nivel 1)",
          "Quién usa Mnemo y con qué sistemas se relaciona")
    # posiciones (x,y,w,h)
    pe = (170, 150, 230, 118)   # Ingeniero QA
    pm = (600, 130, 250, 118)   # Equipo QA / nuevo miembro
    ci = (150, 470, 250, 130)   # CI del cliente
    gh = (1080, 300, 260, 130)  # GitHub
    jx = (1080, 470, 260, 130)  # Jira/Xray
    llm = (1080, 660, 260, 130) # LLM
    sup = (600, 810, 260, 130)  # Supabase
    mn = (590, 470, 280, 160)   # Mnemo (centro)

    box(sv, *pe, "Ingeniero / QA", "[Persona]", "Sube runs, revisa actas, genera planes y automatización", "person", "person")
    box(sv, *pm, "Equipo de QA / nuevo miembro", "[Persona]", "Consulta la memoria del proyecto y el onboarding", "person", "person")
    box(sv, *ci, "Sistema de CI del cliente", "[Sistema externo]", "GitHub Actions · Jenkins · Azure DevOps…", "ext")
    box(sv, *gh, "GitHub", "[Sistema externo]", "Repos, Pull Requests y commit status", "ext")
    box(sv, *jx, "Jira / Xray", "[Sistema externo]", "Bugs, historias de usuario y casos de prueba", "ext")
    box(sv, *llm, "Proveedor LLM", "[Sistema externo]", "Gemini · Groq · Ollama · Anthropic (compatible OpenAI)", "ext")
    box(sv, *sup, "Supabase", "[Sistema externo]", "Auth (identidad) + Postgres gestionado", "ext")
    box(sv, *mn, "Mnemo — QA Memory", "[Software System]",
        "Triaje automático de CI, acta de release firmada y memoria de QA", "system")

    rel(sv, pe, "b", mn, "l", "Usa la aplicación web", "HTTPS", lx=430, ly=430)
    rel(sv, pm, "b", mn, "t", "Consulta memoria / onboarding", "HTTPS")
    rel(sv, ci, "r", mn, "l", "Envía resultados de test", "webhook HMAC")
    rel(sv, mn, "r", gh, "l", "Abre draft PR, publica gate, lee tests", "GitHub App")
    rel(sv, mn, "r", jx, "l", "Importa bugs/HU, exporta casos", "REST")
    rel(sv, mn, "br", llm, "l", "Genera texto en casos ambiguos", "HTTPS / OpenAI API")
    rel(sv, mn, "b", sup, "t", "Persiste datos y verifica identidad", "SQL · JWKS")
    legend(sv, 150, 960)
    return sv.wrap(W, H), W, H

# ============================ NIVEL 2 — CONTENEDORES ============================
def container():
    sv = SVG(); W, H = 1580, 1180
    title(sv, W, "Mnemo — Diagrama de Contenedores (C4 · Nivel 2)",
          "Las piezas desplegables de Mnemo, su tecnología y cómo se comunican")

    # frontera del sistema Mnemo
    bx, by, bw, bh = 430, 120, 720, 940
    sv.add(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="16" fill="none" '
           f'stroke="{SYSTEM[1]}" stroke-width="2" stroke-dasharray="8 6"/>')
    txt(sv, bx+20, by+28, "Mnemo — QA Memory  [Software System]", 13, SYSTEM[1], "700", "start")

    # contenedores internos: spine vertical Web → API → BD, y Reporter a la izquierda
    web = (bx+250, by+70, 360, 140)
    api = (bx+250, by+430, 400, 160)
    dbc = (bx+290, by+760, 300, 150)
    rep = (bx+15, by+445, 180, 130)

    # externos: personas/CI a la izquierda, sistemas a la derecha
    pe  = (110, 150, 220, 118)
    ci  = (110, 470, 220, 118)
    gh  = (1260, 250, 250, 118)
    jx  = (1260, 430, 250, 118)
    llm = (1260, 610, 250, 118)
    sup = (1260, 800, 250, 130)

    box(sv, *pe, "Ingeniero / QA", "[Persona]", "Usa la aplicación web", "person", "person")
    box(sv, *ci, "CI del cliente", "[Sistema externo]", "GitHub Actions · Jenkins…", "ext")
    box(sv, *gh, "GitHub", "[Sistema externo]", "PRs · commit status · repos", "ext")
    box(sv, *jx, "Jira / Xray", "[Sistema externo]", "Bugs · HU · casos", "ext")
    box(sv, *llm, "Proveedor LLM", "[Sistema externo]", "Gemini · Groq · Ollama…", "ext")
    box(sv, *sup, "Supabase Auth", "[Sistema externo]", "GoTrue · JWT · JWKS", "ext")

    box(sv, *web, "Aplicación Web", "[Contenedor: Next.js / React, Vercel]",
        "SPA de QA + proxy server-side /api/v2/*", "cont")
    box(sv, *rep, "Reporter de CI", "[Contenedor: TypeScript]",
        "corre en el CI; emite resultados + DOM", "cont")
    box(sv, *api, "API de aplicación", "[Contenedor: FastAPI / Python 3.13, HF Space · Docker]",
        "Toda la lógica: ingesta (7 formatos) · triaje R0–R6 · acta Ed25519 · memoria/RAG · planes · automatización", "cont")
    box(sv, *dbc, "Base de datos", "[Contenedor: Postgres + pgvector, Supabase]",
        "Runs, Defect DNA, actas, memoria, tenancy · aislamiento RLS", "db", "cyl")

    # relaciones (spine limpio + fan-out a la derecha)
    rel(sv, pe, "r", web, "l", "Usa", "HTTPS", lx=390, ly=250)
    rel(sv, web, "b", api, "t", "Llama a la API /v2/*", "JSON/HTTPS · JWT",
        lx=web[0]+web[2]/2+130, ly=by+320)
    rel(sv, ci, "r", rep, "l", "ejecuta")
    rel(sv, rep, "r", api, "l", "POST /v2/ci/webhook", "HMAC")
    rel(sv, api, "b", dbc, "t", "Lee y escribe", "SQL · pooler")
    rel(sv, api, "r", gh, "l", "PRs, gate", "GitHub App", lx=1160, ly=430)
    rel(sv, api, "r", jx, "l", "Importa / exporta", "REST", lx=1170, ly=515)
    rel(sv, api, "r", llm, "l", "Genera texto", "HTTPS", lx=1165, ly=615)
    rel(sv, api, "br", sup, "tl", "Verifica JWT", "JWKS", lx=1120, ly=740)
    legend(sv, 110, H-40)
    return sv.wrap(W, H), W, H

for name, fn in [("mnemo-c4-context", context), ("mnemo-c4-container", container)]:
    svg, W, H = fn()
    open(f"{name}.svg", "w").write(svg)
    print(f"{name}.svg escrito · {W}x{H}")
