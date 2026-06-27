# Mnemo — Bloque C · C3: PDF del certificado (diseño)

**Fecha:** 2026-06-27 · **Parte de:** Bloque C (demo del concurso), sub-PR 3 de 4 · **Base:** `main` 6354c91 · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Contexto

El Release Assurance Certificate (Ed25519) hoy se ve en HTML (`GET /v2/certificates/{run_id}/html` → `render_html(canonical_json, signature)`, `src/certify/render.py`). El `CertificateCard` del run view muestra verdict/risk_score/firma pero **no permite descargarlo**. Para la demo, el QA Director debe poder **llevarse el certificado en PDF** — un documento oficial, firmado, verificable. (C1 = seed; C2 = UI briefing+ROI; C4 = guion/A-B.)

## Objetivo

Descargar el certificado en **PDF** de un clic, con un **pulido ligero de marca Mnemo** que mejora a la vez el HTML y el PDF.

## Decisiones (confirmadas)

- **Vía:** backend con **xhtml2pdf** (pure-python) — reusa `render_html`, sin libs de sistema (el CSS del cert es simple). Nuevo endpoint `GET /v2/certificates/{run_id}/pdf` → `application/pdf` (attachment).
- **Diseño:** pulido **ligero** del CSS de `render_html` (encabezado con marca "Mnemo", verdict destacado, tipografía/espaciado) — beneficia HTML y PDF. Sin rediseñar.
- **Privacidad:** el PDF se genera local (sin servicios externos), coherente con on-premise / 0€. La **firma Ed25519** aparece en el PDF (documento verificable).

## Componentes

### 1. Dependencia
Añadir `xhtml2pdf` a `requirements.txt` (versión fija, p.ej. `xhtml2pdf==0.2.16`). Es pure-python (no requiere pango/cairo).

### 2. `render_pdf` (`src/certify/render.py`)
Nueva función `render_pdf(cert: Dict[str, Any], signature: str) -> bytes`: llama a `render_html(cert, signature)` y convierte el HTML a PDF con `xhtml2pdf.pisa` (`pisa.CreatePDF(html, dest=buffer)`), devolviendo los bytes. Si la conversión falla (`pisa_status.err`), lanza una excepción clara (el endpoint la traduce a 500/503). Reusa `render_html` — una sola fuente de verdad del contenido.

### 3. Pulido de `render_html` (`src/certify/render.py`)
Añadir un `<style>` en el `<head>` con CSS **compatible con xhtml2pdf** (font-family, márgenes de `@page`/body, color, padding, border-collapse en la tabla, un encabezado con "Mnemo" y el verdict en grande con su color). Mantener todo el contenido actual (identidad, desglose, auto-evaluación, evidencia, firma, disclaimer). No usar flex/grid/svg (xhtml2pdf no los soporta). El verdict ya tiene color por `_VERDICT_COLOR`; destacarlo (tamaño/peso).

### 4. Endpoint `GET /v2/certificates/{run_id}/pdf` (`src/api_v2.py`)
Clonar `get_certificate_html_v2` (misma auth `Depends(get_current_user)` + `service.get(user_id, run_id)`; 404 si no existe; 502 en `psycopg.Error`). Devolver `Response(content=render_pdf(cert["canonical_json"], cert["signature"]), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="certificate-{run_id}.pdf"'})`. Si `render_pdf` falla → 500 con detalle claro.

### 5. Frontend: botón "Descargar PDF" en `CertificateCard`
Como la descarga necesita el token (no es un `<a href>` simple), el botón hace un `fetch` autenticado al `/pdf`, recibe el `blob` y lo descarga (crea un object URL + `<a download>` programático). Añadir un helper al cliente (`getCertificatePdf(token, runId) -> Blob`, vía `apiRequest` o un fetch directo con `Authorization`). El botón solo aparece si hay certificado (`query.data`). Degrada: si la descarga falla, un `toast.error` (no rompe la tarjeta).

## Garantías

- **Una sola fuente de contenido:** el PDF reusa `render_html` (HTML y PDF nunca divergen).
- **Sin libs de sistema:** xhtml2pdf es pure-python (Docker no cambia).
- **Verificable:** la firma Ed25519 y la nota de verificación (`POST /v2/certificates/verify`) están en el PDF.
- **Degradación:** fallo de generación → error claro en el endpoint; fallo de descarga → toast en el frontend.

## Testing

- **Backend (`tests/`):**
  - `render_pdf` devuelve bytes que empiezan por `%PDF` (es un PDF válido) para un cert de ejemplo.
  - `GET /v2/certificates/{id}/pdf` → 200, `content-type: application/pdf`, `Content-Disposition: attachment`, body empieza por `%PDF`; 404 si no existe el cert; auth requerida.
  - `render_html` (tras el pulido) sigue conteniendo verdict/firma/evidencia (no se rompió el contenido).
  - `python3 -m pytest -m "not integration"`.
- **Frontend (vitest):**
  - El botón "Descargar PDF" hace el fetch al endpoint correcto y dispara la descarga del blob (mock fetch → blob; verificar la URL llamada). Toast en error.
  - `npm test` + `tsc`.

## Fuera de alcance

- **C4:** guion 3 actos, push en vivo, aislamiento A/B, ensayo.
- Rediseño completo del certificado (solo pulido ligero); plantillas de cliente/branding configurable; Bloque D (pitch).
