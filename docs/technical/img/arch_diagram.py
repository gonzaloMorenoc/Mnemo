# -*- coding: utf-8 -*-
"""Genera el diagrama de arquitectura de Mnemo como SVG (vectorial, alta nitidez)."""
from html import escape

W, H = 1720, 1176
parts = []

def add(s): parts.append(s)

def rrect(x, y, w, h, r, fill, stroke="none", sw=0, opacity=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"{d}/>')

def text(x, y, s, size, fill="#0f172a", weight="400", anchor="start", family="sans", spacing=None):
    fam = ("'Menlo','SF Mono','DejaVu Sans Mono',monospace" if family == "mono"
           else "'Helvetica Neue',Helvetica,Arial,'Segoe UI',sans-serif")
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
        f'text-anchor="{anchor}" font-family="{fam}"{ls}>{escape(s)}</text>')

def pill(x, y, s, size=10.5, fill="#eef2f7", tc="#475569", pad=7):
    w = len(s) * size * 0.60 + pad * 2
    rrect(x, y, w, size + 8, (size + 8) / 2, fill)
    text(x + pad, y + size + 0.5, s, size, tc, "500", family="mono")
    return w

def pill_row(x, y, items, size=10.5, fill="#eef2f7", tc="#475569", gap=6):
    cx = x
    for it in items:
        cx += pill(cx, y, it, size, fill, tc) + gap
    return cx

# marker defs
CANVAS = W  # lienzo cuadrado: evita que qlmanage recorte al forzar thumbnail cuadrado
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS*2}" height="{CANVAS*2}" viewBox="0 0 {W} {CANVAS}">')
add('<defs>')
for name, col in [("req", "#334155"), ("auth", "#2563eb"), ("ext", "#ea580c"), ("data", "#15803d")]:
    add(f'<marker id="a{name}" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">'
        f'<path d="M0,0 L7,3 L0,6 Z" fill="{col}"/></marker>')
add('<linearGradient id="hdr" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#0b1220"/><stop offset="1" stop-color="#111a2e"/></linearGradient>')
add('</defs>')

# background (cuadrado; el contenido ocupa la parte superior, el resto es blanco y se recorta)
rrect(0, 0, W, CANVAS, 0, "#f5f7fb")

def arrow(x1, y1, x2, y2, kind="req", label=None, lx=None, ly=None, curve=0):
    col = {"req": "#334155", "auth": "#2563eb", "ext": "#ea580c", "data": "#15803d"}[kind]
    dash = {"req": None, "auth": "6 4", "ext": "2 5", "data": "8 4"}[kind]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    if curve:
        mx = (x1 + x2) / 2
        add(f'<path d="M{x1},{y1} C{mx},{y1+curve} {mx},{y2-curve} {x2},{y2}" fill="none" '
            f'stroke="{col}" stroke-width="2.2" marker-end="url(#a{kind})"{d}/>')
    else:
        add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="2.2" '
            f'marker-end="url(#a{kind})"{d}/>')
    if label:
        text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2,
             label, 10.5, col, "600", "middle", family="mono")

# ---------------- Title ----------------
text(50, 52, "Mnemo — Arquitectura del sistema", 30, "#0f172a", "700")
text(50, 78, "QA Memory · plataforma de memoria operativa de QA — triaje automático · acta de release firmada · memoria de QA",
     14.5, "#5b6b82", "400")
text(W - 50, 52, "v0.4 · 2026-07", 13, "#8a97a8", "500", "end", family="mono")
text(W - 50, 72, "3 planos: Vercel · HF Space · Supabase", 12, "#8a97a8", "500", "end", family="mono")

MX = 50            # left margin
CW = W - 2 * MX    # content width

def band_header(x, y, label, color, tag=None):
    add(f'<circle cx="{x+11}" cy="{y}" r="5.5" fill="{color}"/>')
    text(x + 26, y + 5, label, 16, "#0f172a", "700")
    if tag:
        text(x + 26 + len(label) * 9.4 + 14, y + 5, tag, 12.5, "#7686a0", "500", family="mono")

# ================= BAND 1 — Actores y fuentes =================
b1y = 104
band_header(MX, b1y, "Actores y fuentes de datos", "#6366f1")
cy = b1y + 18
cards1 = [
    ("👤  QA / Test Engineer", "usa la aplicación en el navegador", []),
    ("⚙️  CI del cliente", "GitHub Actions · Jenkins · Azure…", ["webhook HMAC", "reporter Playwright"]),
    ("🐙  Repositorio GitHub", "tests + código · Pull Requests", ["GitHub App"]),
    ("🗂️  Jira / Xray", "bugs · historias de usuario · casos", ["API token (Fernet)"]),
]
cw1 = (CW - 3 * 18) / 4
for i, (t, sub, pills) in enumerate(cards1):
    x = MX + i * (cw1 + 18)
    rrect(x, cy, cw1, 78, 12, "#ffffff", "#dbe2ec", 1.4)
    rrect(x, cy, 5, 78, 2, "#6366f1")
    text(x + 16, cy + 26, t, 13.5, "#1f2a3d", "700")
    text(x + 16, cy + 45, sub, 11, "#64748b")
    if pills: pill_row(x + 16, cy + 54, pills, 10)

# ================= BAND 2 — Vercel Frontend =================
b2y = 230
zx, zy, zw, zh = MX, b2y, CW, 116
rrect(zx, zy, zw, zh, 14, "#eef1f6", "#cfd8e3", 1.4)
add(f'<circle cx="{zx+20}" cy="{zy+24}" r="6" fill="#0f172a"/>')
text(zx + 34, zy + 29, "Vercel", 15.5, "#0f172a", "700")
text(zx + 34 + 62, zy + 29, "— Frontend (edge/CDN)", 12.5, "#64748b", "500", family="mono")
# cards inside
fcw = (zw - 3 * 20) / 2
fx = zx + 20
rrect(fx, zy + 42, fcw, 58, 10, "#ffffff", "#dbe2ec", 1.3)
text(fx + 14, zy + 64, "Next.js App · App Router", 13, "#1f2a3d", "700")
text(fx + 14, zy + 82, "páginas /verify (pública) · /app/* (autopilot, assurance, defects, knowledge, test-plan, graph, onboarding, calibration…)", 10.3, "#64748b")
pill_row(fx + 14, zy + 88, ["React 19", "TypeScript", "TanStack Query", "shadcn/ui", "Tailwind", "Supabase JS"], 10)
fx2 = fx + fcw + 20
rrect(fx2, zy + 42, fcw, 58, 10, "#ffffff", "#dbe2ec", 1.3)
text(fx2 + 14, zy + 64, "Proxy server-side · /api/v2/*", 13, "#1f2a3d", "700")
text(fx2 + 14, zy + 82, "route handlers reenvían al backend · propagan el JWT · sin CORS", 10.5, "#64748b")
pill_row(fx2 + 14, zy + 88, ["NEXT_PUBLIC_API_BASE_URL", "maxDuration 60s"], 10)

# ================= BAND 3 — HF Space Backend =================
b3y = 372
bh = 386
rrect(MX, b3y, CW, bh, 16, "#e9f4f7", "#b6dde7", 1.6)
add(f'<rect x="{MX}" y="{b3y}" width="{CW}" height="34" rx="16" fill="url(#hdr)"/>')
add(f'<rect x="{MX}" y="{b3y+18}" width="{CW}" height="16" fill="url(#hdr)"/>')
text(MX + 18, b3y + 23, "🤗  Hugging Face Space — Backend", 15, "#ffffff", "700")
text(MX + 18 + 350, b3y + 23, "Docker · uvicorn asgi:app · :8080 · keep-warm (GitHub Action /15 min)", 11.5, "#9fb3d6", "500", family="mono")
# API strip
ax, ay = MX + 18, b3y + 46
rrect(ax, ay, CW - 36, 46, 9, "#ffffff", "#c7dbe2", 1.3)
text(ax + 14, ay + 20, "FastAPI  ·  router /v2", 13, "#0e7490", "700")
text(ax + 150, ay + 20, "· capa de API + orquestación", 11.5, "#5b7683", "500")
pill_row(ax + 14, ay + 27, ["Python 3.13", "auth Supabase JWT (JWKS)", "pool psycopg pre-calentado",
                            "deps perezosas", "cota INGEST_MAX_BYTES", "defusedxml"], 10, "#e4f0f4", "#0e7490")

# modules grid
mods = [
    ("Ingest", "7 parsers + autodetección", "#0891b2"),
    ("Defects / DNA", "familias · fingerprint · centroide", "#0891b2"),
    ("Triage", "reglas R0–R6 · LLM solo ambiguos", "#0891b2"),
    ("Actions", "self-heal · quarantine · ticket", "#0891b2"),
    ("Certify  ★", "acta firmada Ed25519 · gate", "#7c3aed"),
    ("Knowledge", "memoria QA (7 tipos) · RAG", "#0891b2"),
    ("Graph", "grafo + coverage gaps reales", "#0891b2"),
    ("TestPlan", "HU → plan · export Xray", "#0891b2"),
    ("Automation", "caso → Playwright .spec.ts", "#0891b2"),
    ("Repo ingest", "indexa los tests del repo", "#0891b2"),
    ("Onboarding", "resumen de dominio + ruta", "#0891b2"),
    ("CI", "webhook HMAC · GitHub App", "#0891b2"),
    ("Orgs", "crear · join · list", "#0891b2"),
    ("Integrations", "Jira · GitHub · Xray (Fernet)", "#0891b2"),
]
cols = 7
gx = MX + 18
gy = ay + 60
gap = 12
mcw = (CW - 36 - (cols - 1) * gap) / cols
mch = 74
text(gx, gy - 8, "Módulos de capacidad  ·  src/", 12, "#0e7490", "700")
for i, (t, sub, col) in enumerate(mods):
    r, c = divmod(i, cols)
    x = gx + c * (mcw + gap)
    y = gy + r * (mch + gap)
    hl = col == "#7c3aed"
    rrect(x, y, mcw, mch, 9, "#fbf8ff" if hl else "#ffffff", col if hl else "#cbd9e0", 1.6 if hl else 1.2)
    rrect(x, y, mcw, 4, 2, col)
    text(x + 11, y + 27, t, 12.5, "#4c1d95" if hl else "#164e63", "700")
    # wrap subtitle to 2 lines
    words = sub.split()
    line, lines = "", []
    for wd in words:
        if len(line + " " + wd) > 26:
            lines.append(line); line = wd
        else:
            line = (line + " " + wd).strip()
    lines.append(line)
    for j, ln in enumerate(lines[:2]):
        text(x + 11, y + 45 + j * 13, ln, 10, "#64748b")

# engine services strip
ey = gy + 2 * (mch + gap) + 14
text(gx, ey - 8, "Servicios del motor", 12, "#0e7490", "700")
eng = [
    ("Embeddings — LOCAL", "all-MiniLM-L6-v2 · 384d · CPU (torch)", "#059669"),
    ("Firma Ed25519", "cryptography · key_id · /verify público", "#7c3aed"),
    ("Sanitizer", "redacta secretos y PII antes de persistir", "#dc2626"),
    ("LLM factory", "OpenAI-compat · Ollama · Anthropic", "#0891b2"),
]
ecw = (CW - 36 - 3 * gap) / 4
for i, (t, sub, col) in enumerate(eng):
    x = gx + i * (ecw + gap)
    rrect(x, ey, ecw, 52, 9, "#ffffff", "#cbd9e0", 1.2)
    rrect(x, ey, 4, 52, 2, col)
    text(x + 13, ey + 22, t, 12, col, "700")
    text(x + 13, ey + 40, sub, 10, "#64748b")

# ================= BAND 4 — Supabase =================
b4y = b3y + bh + 26
sh = 150
rrect(MX, b4y, CW, sh, 14, "#eafaf1", "#b7e6cd", 1.5)
add(f'<circle cx="{MX+20}" cy="{b4y+24}" r="6" fill="#16a34a"/>')
text(MX + 34, b4y + 29, "Supabase", 15.5, "#0f172a", "700")
text(MX + 34 + 92, b4y + 29, "— Datos gestionados & Auth", 12.5, "#5b7683", "500", family="mono")
# postgres card
pcw = CW * 0.62
px, py = MX + 20, b4y + 42
rrect(px, py, pcw, 92, 10, "#ffffff", "#c5e6d3", 1.3)
text(px + 14, py + 24, "Postgres + pgvector", 13.5, "#15803d", "700")
text(px + 14 + 175, py + 24, "· 20 tablas · RLS + FORCE", 11, "#5b7683", "500", family="mono")
left_groups = [
    ("Runs & fallos", "test_runs · failures · test_results · dom_snapshots"),
    ("Defect DNA", "defect_families · triage_verdicts · triage_corrections"),
    ("Actas & acciones", "certificates · actions"),
]
right_groups = [
    ("Conocimiento", "qa_knowledge · test_assets"),
    ("Tenancy", "organizations · memberships · org_integrations"),
]
for j, (g, tbls) in enumerate(left_groups):
    yy = py + 44 + j * 17
    text(px + 14, yy, g, 10, "#15803d", "700", family="mono")
    text(px + 14 + 120, yy, tbls, 9.6, "#64748b", family="mono")
for j, (g, tbls) in enumerate(right_groups):
    yy = py + 44 + j * 17
    cx0 = px + pcw * 0.54
    text(cx0, yy, g, 10, "#15803d", "700", family="mono")
    text(cx0 + 100, yy, tbls, 9.6, "#64748b", family="mono")
# auth card
acx = px + pcw + 20
acw = CW - 20 - pcw - 20
rrect(acx, py, acw, 44, 10, "#ffffff", "#c5e6d3", 1.3)
text(acx + 14, py + 24, "Auth · GoTrue", 13, "#15803d", "700")
text(acx + 14, py + 40, "JWT ES256/RS256 · verificación por JWKS", 10, "#64748b")
# isolation badge
rrect(acx, py + 52, acw, 40, 10, "#f0fdf4", "#86efac", 1.3)
text(acx + 14, py + 70, "🔒 Aislamiento multi-tenant", 11.5, "#166534", "700")
text(acx + 14, py + 85, "RLS + filtro por membership · probado con tests", 9.8, "#3f6b4e")

# ================= BAND 5 — Externos =================
b5y = b4y + sh + 26
eh = 104
band_header(MX, b5y, "Servicios externos", "#ea580c")
ext = [
    ("🧠  Proveedor LLM", "Google Gemini (free, OpenAI-compat) · Groq · Ollama · Anthropic", ["ALLOW_EXTERNAL_LLM"]),
    ("🐙  GitHub App", "commit status (quality gate) · draft PR (self-heal / automation)", ["nunca auto-merge"]),
    ("🗂️  Jira / Xray API", "pull de bugs · export de casos de prueba", []),
]
ecw2 = (CW - 2 * 18) / 3
for i, (t, sub, pills) in enumerate(ext):
    x = MX + i * (ecw2 + 18)
    y = b5y + 16
    rrect(x, y, ecw2, 74, 12, "#fff7ed", "#fdba74", 1.4)
    rrect(x, y, 5, 74, 2, "#ea580c")
    text(x + 16, y + 26, t, 13.5, "#9a3412", "700")
    text(x + 16, y + 45, sub, 10.3, "#7c5230")
    if pills: pill_row(x + 16, y + 53, pills, 10, "#ffedd5", "#9a3412")

# ================= ARROWS =================
# QA -> Vercel
arrow(MX + cw1 / 2, b1y + 18 + 78, MX + cw1 / 2, b2y, "req")
arrow(MX + cw1/2, (b1y+96+b2y)/2, MX+cw1/2, (b1y+96+b2y)/2, "req")  # noop keep
# Vercel proxy -> Backend API (JWT)
arrow(fx2 + fcw / 2, b2y + zh, fx2 + fcw / 2, b3y, "auth", "HTTPS + JWT", fx2 + fcw/2 + 70, (b2y+zh+b3y)/2 + 4)
# CI del cliente -> Backend (webhook) bypass
x_ci = MX + (cw1 + 18) * 1 + cw1 / 2
add(f'<path d="M{x_ci},{b1y+96} C{x_ci},{b1y+150} {W-90},{b1y+150} {W-90},{b3y+120} '
    f'L{MX+CW},{b3y+120}" fill="none" stroke="#ea580c" stroke-width="2.2" '
    f'stroke-dasharray="2 5" marker-end="url(#aext)"/>')
text(W - 300, b1y + 145, "webhook HMAC  (POST /v2/ci/webhook)", 10.5, "#ea580c", "600", "middle", family="mono")
# Backend -> Supabase (data)
arrow(MX + CW * 0.35, b3y + bh, MX + CW * 0.35, b4y, "data", "SQL (pooler)", MX + CW*0.35 - 62, (b3y+bh+b4y)/2 + 4)
# Backend Auth verify -> Supabase auth (JWKS)
arrow(MX + CW * 0.60, b4y, MX + CW * 0.60, b3y + bh, "auth", "JWKS", MX + CW*0.60 + 34, (b3y+bh+b4y)/2 + 4)
# Backend -> External (down)
arrow(MX + CW * 0.5, b4y + sh, MX + CW * 0.5, b5y, "ext", "API calls (LLM · GitHub · Jira)", MX + CW*0.5, (b4y+sh+b5y)/2 + 4)

# ================= FOOTER legend =================
fy = b5y + eh + 20
rrect(MX, fy, CW, 66, 12, "#ffffff", "#dbe2ec", 1.3)
# arrow legend
text(MX + 18, fy + 22, "Flujos:", 11.5, "#0f172a", "700")
def leg(x, y, col, dash, lbl):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<line x1="{x}" y1="{y}" x2="{x+34}" y2="{y}" stroke="{col}" stroke-width="2.4"{d}/>')
    text(x + 42, y + 4, lbl, 10.5, "#475569", "500")
leg(MX + 78, fy + 18, "#334155", None, "petición")
leg(MX + 210, fy + 18, "#2563eb", "6 4", "auth JWT")
leg(MX + 350, fy + 18, "#ea580c", "2 5", "llamada externa / webhook")
leg(MX + 560, fy + 18, "#15803d", "8 4", "acceso a datos")
# differentiator
rrect(MX + 18, fy + 34, CW * 0.60, 22, 6, "#f5f0ff")
text(MX + 30, fy + 49, "★ Diferenciador: acta de release firmada Ed25519 y verificable por cualquiera en /verify (sin cuenta) — “SLSA para QA”.",
     11, "#5b21b6", "600")
# ops note
text(W - 66, fy + 26, "Despliegue: frontend en Vercel · backend en HF Space (clona main en build →", 10.3, "#64748b", "500", "end", family="mono")
text(W - 66, fy + 42, "cada deploy = factory rebuild) · BD+Auth en Supabase · embeddings locales, LLM por API.", 10.3, "#64748b", "500", "end", family="mono")

add('</svg>')

svg = "\n".join(parts)
open("mnemo-arquitectura.svg", "w").write(svg)
print("SVG escrito:", len(svg), "bytes ·", W, "x", H)
