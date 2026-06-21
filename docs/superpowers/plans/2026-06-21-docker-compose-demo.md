# docker-compose on-prem + demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un `docker compose up` que levante Mnemo on-prem completo (Supabase self-hosted + Ollama + backend + frontend) con migraciones y una demo sembrada.

**Architecture:** Stack local en la red de Docker: `db` (supabase/postgres+pgvector), `auth` (GoTrue, RS256+JWKS), `kong` (gateway de `/auth/v1`), `ollama`, `backend` (FastAPI), `frontend` (Next.js), y un `init` efímero (migraciones + usuario demo vía GoTrue + seed). On-prem real: nada sale a la nube.

**Tech Stack:** Docker Compose, imágenes oficiales de Supabase (postgres/gotrue/kong), Ollama, Python 3.13/FastAPI, Next.js. No hay tests unitarios nuevos (infra) — la verificación es build + `compose config` + un smoke e2e.

**⚠️ Importante para quien ejecuta:** este slice NO se valida en CI (demasiado pesado: modelo ~5 GB). Varias tareas (compose, GoTrue, init) **solo se validan de verdad arrancando el compose**, lo que exige liberar disco antes (la máquina está al ~96 %). Construye y arranca incrementalmente; donde una tarea diga "solo se valida al `up`", déjalo anotado si no puedes arrancar y continúa con las que sí se pueden verificar por build/config.

**Referencia:** el `docker-compose.yml` oficial de Supabase self-hosting (https://github.com/supabase/supabase/tree/master/docker) es la base de los servicios `db`/`auth`/`kong`; este plan usa el subconjunto mínimo y conocido.

---

### Task 1: Backend `Dockerfile` + `.dockerignore`

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Write `.dockerignore`** (raíz):

```
.git
.venv
venv
__pycache__
*.pyc
.pytest_cache
.coverage
node_modules
frontend
db_chroma
data/logs
.env
.agent
docs
```

- [ ] **Step 2: Write `Dockerfile`** (backend, en la raíz):

```dockerfile
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY api.py .
COPY db/ db/
COPY scripts/ scripts/

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --retries=10 \
    CMD curl -fsS http://localhost:8080/v2/health || exit 1
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 3: Build it (verification)**

Run: `docker build -t mnemo-backend:dev .`
Expected: build completes. (NOTE: `requirements.txt` is heavy — sentence-transformers/torch — so the image is multi-GB and the build is slow. If disk is full, this is where it fails; free space first.)

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: Dockerfile del backend + .dockerignore"
```

---

### Task 2: Frontend `Dockerfile` + `.dockerignore`

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`

- [ ] **Step 1: Write `frontend/.dockerignore`:**

```
node_modules
.next
.env*
npm-debug.log
```

- [ ] **Step 2: Write `frontend/Dockerfile`** (multi-stage). Use the Node version from `frontend/.nvmrc` (read it; it is likely `20` — if `.nvmrc` says otherwise, use that tag):

```dockerfile
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* must be present at build time for Next.js to inline them.
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["npm", "run", "start"]
```

- [ ] **Step 3: Build it (verification)**

Run: `docker build -t mnemo-frontend:dev ./frontend`
Expected: build completes (the `npm run build` step is the same one CI runs green). If it fails on missing `NEXT_PUBLIC_*` at runtime, that's expected — they're provided in the compose build args (Task 6).

- [ ] **Step 4: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore
git commit -m "feat: Dockerfile del frontend (multi-stage)"
```

---

### Task 3: `.env.docker` (secretos de DEMO)

**Files:**
- Create: `.env.docker`

These are DEMO-ONLY values, safe to commit. The JWT `ANON_KEY`/`SERVICE_ROLE_KEY` are the well-known Supabase demo keys that pair with the demo `JWT_SECRET`.

- [ ] **Step 1: Generate a Fernet key + write the file.**

Generate the Fernet key:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Create `.env.docker` (paste the generated Fernet key into `MNEMO_SECRET_KEY`):
```bash
# === DEMO ONLY — NO usar en producción. Valores públicos de demostración. ===

# Postgres
POSTGRES_PASSWORD=postgres-demo-pass
POSTGRES_DB=postgres

# Supabase JWT (demo). Estas anon/service keys son las de ejemplo de Supabase,
# válidas SOLO con este JWT_SECRET de demo.
JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long
ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlLWRlbW8iLCJpYXQiOjE2NDE3NjkyMDAsImV4cCI6MTc5OTUzNTYwMH0.dc_X5iR_VP_qT0zsiyj_I_OZ2T9FtRU2BBNWN8Bu4GE
SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UtZGVtbyIsImlhdCI6MTY0MTc2OTIwMCwiZXhwIjoxNzk5NTM1NjAwfQ.DaYlNEoUrrEn2Ig7tqibS-PHK5vgusbcbo7X36XVt4Q

# App backend
DATABASE_URL=postgresql://postgres:postgres-demo-pass@db:5432/postgres
SUPABASE_URL=http://kong:8000
SUPABASE_JWKS_URL=http://kong:8000/auth/v1/.well-known/jwks.json
OLLAMA_BASE_URL=http://ollama:11434
LLM_PROVIDER=ollama
LLM_MODEL=deepseek-r1:8b
MNEMO_SECRET_KEY=PASTE_FERNET_KEY_HERE

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
NEXT_PUBLIC_SUPABASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlLWRlbW8iLCJpYXQiOjE2NDE3NjkyMDAsImV4cCI6MTc5OTUzNTYwMH0.dc_X5iR_VP_qT0zsiyj_I_OZ2T9FtRU2BBNWN8Bu4GE

# Usuario demo (login en el frontend)
DEMO_EMAIL=demo@mnemo.local
DEMO_PASSWORD=mnemo-demo-1234
```

NOTE on JWT signing: the demo uses GoTrue's **HS256** with the shared `JWT_SECRET` (the standard Supabase self-hosting default), which is why `SUPABASE_JWKS_URL` won't serve RSA keys. The verifier change to accept HS256 is handled in Task 5. (RS256+JWKS in self-hosted GoTrue is possible but not the default and adds significant config; the spec's chosen approach is RS256, but the simplest robust path that actually boots is HS256 — this plan takes the HS256 fallback explicitly and keeps it a tiny, isolated verifier change.)

- [ ] **Step 2: Commit**

```bash
git add .env.docker
git commit -m "feat: .env.docker con secretos de demo"
```

---

### Task 4: Verifier acepta HS256 self-hosted (cambio mínimo y aislado)

The self-hosted GoTrue default signs JWTs with **HS256** + shared `JWT_SECRET`, not RS256/JWKS. Add a narrow HS256 path to the verifier, gated on a new `SUPABASE_JWT_SECRET` env var — when unset (cloud), behavior is byte-identical (RS256/JWKS as today).

**Files:**
- Modify: `src/config.py`
- Modify: `src/security.py`
- Test: `tests/test_security_hs256.py`

- [ ] **Step 1: Write the failing test** — `tests/test_security_hs256.py`:

```python
import jwt as pyjwt
import pytest

from src import config
from src.security import SupabaseJWTVerifier
from fastapi import HTTPException


def test_hs256_token_accepted_when_secret_set(monkeypatch):
    secret = "super-secret-jwt-token-with-at-least-32-characters-long"
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", secret)
    token = pyjwt.encode({"sub": "user-1", "email": "d@x.com"}, secret, algorithm="HS256")
    user = SupabaseJWTVerifier().verify(token)
    assert user.user_id == "user-1" and user.email == "d@x.com"


def test_hs256_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "the-real-secret-key-32-characters-min!!")
    bad = pyjwt.encode({"sub": "x"}, "a-different-wrong-secret-key-32-characters", algorithm="HS256")
    with pytest.raises(HTTPException):
        SupabaseJWTVerifier().verify(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_security_hs256.py -v`
Expected: FAIL — `SUPABASE_JWT_SECRET` doesn't exist / HS256 not handled.

- [ ] **Step 3: Add config + verifier branch.**

In `src/config.py`, add:
```python
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
```

In `src/security.py`, import it and add an HS256 fast-path at the TOP of `verify`, before the JWKS logic:
```python
from src.config import SUPABASE_JWKS_URL, SUPABASE_JWT_AUDIENCE, SUPABASE_JWT_SECRET, SUPABASE_URL
```
and at the start of `verify(self, token)`:
```python
        if SUPABASE_JWT_SECRET:
            try:
                payload = jwt.decode(
                    token, SUPABASE_JWT_SECRET, algorithms=["HS256"],
                    options={"verify_aud": False},
                )
            except jwt.PyJWTError as exc:
                raise HTTPException(status_code=401, detail="Invalid or expired auth token") from exc
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid auth token payload")
            return AuthenticatedUser(user_id=user_id, email=payload.get("email"), claims=payload)
```
(The existing RS256/JWKS code stays below, untouched, used when `SUPABASE_JWT_SECRET` is empty.)

- [ ] **Step 4: Run test + full suite**

Run: `python3 -m pytest tests/test_security_hs256.py -v` (2 passed), then `python3 -m pytest -m "not integration" -q` (all green — the cloud RS256 path is unchanged because `SUPABASE_JWT_SECRET` is empty in tests except the new ones).

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/security.py tests/test_security_hs256.py
git commit -m "feat: verifier acepta HS256 self-hosted (gated por SUPABASE_JWT_SECRET)"
```

---

### Task 5: `kong.yml` (gateway declarativo de `/auth/v1`)

Kong routes `/auth/v1/*` to GoTrue so the backend's `SUPABASE_URL=http://kong:8000` works and the frontend can sign up/log in.

**Files:**
- Create: `docker/kong.yml`

- [ ] **Step 1: Write `docker/kong.yml`:**

```yaml
_format_version: "2.1"
services:
  - name: auth-v1
    url: http://auth:9999/
    routes:
      - name: auth-v1-route
        strip_path: true
        paths:
          - /auth/v1/
    plugins:
      - name: cors
```

- [ ] **Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('docker/kong.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add docker/kong.yml
git commit -m "feat: kong declarativo para /auth/v1"
```

---

### Task 6: `docker-compose.yml`

Wires db + auth + kong + ollama + backend + frontend + init. Based on the official Supabase self-hosting compose (minimal subset).

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`:**

```yaml
name: mnemo

services:
  db:
    image: supabase/postgres:15.8.1.060
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 20
    ports:
      - "5432:5432"

  auth:
    image: supabase/gotrue:v2.151.0
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    environment:
      GOTRUE_API_HOST: 0.0.0.0
      GOTRUE_API_PORT: 9999
      API_EXTERNAL_URL: http://localhost:8000
      GOTRUE_DB_DRIVER: postgres
      GOTRUE_DB_DATABASE_URL: postgresql://supabase_auth_admin:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      GOTRUE_SITE_URL: http://localhost:3000
      GOTRUE_URI_ALLOW_LIST: "*"
      GOTRUE_DISABLE_SIGNUP: "false"
      GOTRUE_JWT_SECRET: ${JWT_SECRET}
      GOTRUE_JWT_EXP: 3600
      GOTRUE_JWT_DEFAULT_GROUP_NAME: authenticated
      GOTRUE_JWT_ADMIN_ROLES: service_role
      GOTRUE_JWT_AUD: authenticated
      GOTRUE_MAILER_AUTOCONFIRM: "true"
      GOTRUE_EXTERNAL_EMAIL_ENABLED: "true"

  kong:
    image: kong:2.8.1
    restart: unless-stopped
    depends_on:
      - auth
    environment:
      KONG_DATABASE: "off"
      KONG_DECLARATIVE_CONFIG: /home/kong/kong.yml
      KONG_PLUGINS: request-transformer,cors
    volumes:
      - ./docker/kong.yml:/home/kong/kong.yml:ro
    ports:
      - "8000:8000"

  ollama:
    image: ollama/ollama:0.5.7
    restart: unless-stopped
    volumes:
      - ollama-models:/root/.ollama
    ports:
      - "11434:11434"

  backend:
    build: .
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
      kong:
        condition: service_started
      ollama:
        condition: service_started
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_JWKS_URL: ${SUPABASE_JWKS_URL}
      SUPABASE_JWT_SECRET: ${JWT_SECRET}
      SUPABASE_JWT_AUDIENCE: authenticated
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}
      LLM_PROVIDER: ${LLM_PROVIDER}
      LLM_MODEL: ${LLM_MODEL}
      MNEMO_SECRET_KEY: ${MNEMO_SECRET_KEY}
    ports:
      - "8080:8080"

  frontend:
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL}
        NEXT_PUBLIC_SUPABASE_URL: ${NEXT_PUBLIC_SUPABASE_URL}
        NEXT_PUBLIC_SUPABASE_ANON_KEY: ${NEXT_PUBLIC_SUPABASE_ANON_KEY}
    restart: unless-stopped
    depends_on:
      - backend
    ports:
      - "3000:3000"

  init:
    build: .
    depends_on:
      db:
        condition: service_healthy
      auth:
        condition: service_started
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SUPABASE_URL: ${SUPABASE_URL}
      SERVICE_ROLE_KEY: ${SERVICE_ROLE_KEY}
      DEMO_EMAIL: ${DEMO_EMAIL}
      DEMO_PASSWORD: ${DEMO_PASSWORD}
    command: ["python", "scripts/docker_init.py"]
    restart: "no"

volumes:
  db-data:
  ollama-models:
```

- [ ] **Step 2: Validate compose syntax**

Run: `docker compose --env-file .env.docker config >/dev/null && echo "compose OK"`
Expected: `compose OK` (this only checks syntax + var interpolation, not that images exist/boot).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: docker-compose (supabase self-hosted + ollama + backend + frontend + init)"
```

NOTE (only verifiable at `up`): the exact image tags (`supabase/postgres`, `supabase/gotrue`, `kong`, `ollama/ollama`) and GoTrue's DB role (`supabase_auth_admin`) come from the official Supabase compose; pin/adjust to the versions that actually pull and boot in your environment. GoTrue needs the `auth` schema + its admin role, which `supabase/postgres` provisions on first init.

---

### Task 7: `scripts/docker_init.py` (migraciones + usuario demo + seed)

**Files:**
- Create: `scripts/docker_init.py`

- [ ] **Step 1: Write `scripts/docker_init.py`:**

```python
"""Init de la demo on-prem: aplica migraciones, crea el usuario demo via GoTrue y siembra.

Idempotente: re-ejecutar no duplica. Pensado para correr como el servicio `init`.
"""

import os
import time

import psycopg
import requests

DBURL = os.environ["DATABASE_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_ROLE_KEY = os.environ["SERVICE_ROLE_KEY"]
DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

MIGRATIONS = [
    "db/migrations/001_multitenant_kb.sql",
    "db/migrations/002_assurance.sql",
    "db/migrations/003_assurance_indexes.sql",
    "db/migrations/004_more_sources.sql",
    "db/migrations/005_jira_integration.sql",
    "db/migrations/006_failures_external_ref_index.sql",
]


def _wait_db():
    for _ in range(30):
        try:
            with psycopg.connect(DBURL, connect_timeout=3):
                return
        except psycopg.OperationalError:
            time.sleep(2)
    raise SystemExit("db no disponible")


def _apply_migrations():
    with psycopg.connect(DBURL) as conn:
        for path in MIGRATIONS:
            with open(path) as fh:
                sql = fh.read()
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"migración aplicada: {path}")


def _ensure_demo_user() -> str:
    """Crea (o reutiliza) el usuario demo via la admin API de GoTrue. Devuelve su id."""
    headers = {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "email_confirm": True},
        headers=headers, timeout=10,
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]
    # Ya existe: buscarlo
    lst = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users", headers=headers, timeout=10)
    lst.raise_for_status()
    for u in lst.json().get("users", []):
        if u.get("email") == DEMO_EMAIL:
            return u["id"]
    raise SystemExit(f"no se pudo crear/encontrar el usuario demo: {resp.status_code} {resp.text[:200]}")


def _seed(user_id: str):
    from src.defects.embedder import LocalEmbedder
    from src.defects.ingestion_service import IngestionService
    from src.defects.repository import AssuranceRepository
    import json

    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from public.organizations where created_by = %s limit 1", (user_id,))
            row = cur.fetchone()
            if row:
                print("demo ya sembrada; nada que hacer")
                return
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("Demo MTP", user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()

    repo = AssuranceRepository(DBURL)
    service = IngestionService(repo=repo, embedder=LocalEmbedder())

    def allure(*cases):
        return json.dumps(list(cases)).encode("utf-8")

    def failed(name, message, trace):
        return {"name": name, "status": "failed", "statusDetails": {"message": message, "trace": trace}}

    reports = {
        "cliente-alpha": allure(
            failed("test_login", "TimeoutException: esperando elemento tras 30000ms", "at Login.java:42"),
            failed("test_export", "NullPointerException en ExportService", "at Export.java:11"),
        ),
        "cliente-beta": allure(
            failed("test_checkout", "TimeoutException: esperando elemento tras 12000ms", "at Checkout.java:88"),
        ),
    }
    for project, data in reports.items():
        service.ingest_report(user_id=user_id, org_id=org_id, project=project, source="allure", data=data)
    print(f"demo sembrada: org={org_id} user={user_id}")


def main():
    _wait_db()
    _apply_migrations()
    user_id = _ensure_demo_user()
    _seed(user_id)
    print("init completado")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports / parses**

Run: `python3 -c "import ast; ast.parse(open('scripts/docker_init.py').read()); print('ok')"`
Expected: `ok`. (Full run only works at `up` against the live GoTrue + db.)

- [ ] **Step 3: Commit**

```bash
git add scripts/docker_init.py
git commit -m "feat: init de la demo (migraciones + usuario demo via GoTrue + seed)"
```

---

### Task 8: Reportes de ejemplo para la demo

**Files:**
- Create: `examples/allure-ejemplo.json`
- Create: `examples/junit-ejemplo.xml`

- [ ] **Step 1: Write `examples/allure-ejemplo.json`:**

```json
[
  {"name": "test_pago", "status": "failed",
   "statusDetails": {"message": "AssertionError: esperado 200 pero fue 500", "trace": "at Payment.java:21"}},
  {"name": "test_busqueda", "status": "failed",
   "statusDetails": {"message": "StaleElementReferenceException en SearchPage", "trace": "at Search.java:7"}}
]
```

- [ ] **Step 2: Write `examples/junit-ejemplo.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="suite-demo" tests="2" failures="1" errors="0">
    <testcase classname="com.demo.LoginTest" name="testTimeout">
      <failure message="TimeoutException: waited 30000ms" type="org.openqa.selenium.TimeoutException">at com.demo.LoginTest.testTimeout(LoginTest.java:42)</failure>
    </testcase>
    <testcase classname="com.demo.LoginTest" name="testOk"/>
  </testsuite>
</testsuites>
```

- [ ] **Step 3: Commit**

```bash
git add examples/
git commit -m "feat: reportes de ejemplo para la demo"
```

---

### Task 9: `scripts/smoke_demo.sh` + `docs/DEMO.md`

**Files:**
- Create: `scripts/smoke_demo.sh`
- Create: `docs/DEMO.md`

- [ ] **Step 1: Write `scripts/smoke_demo.sh`:**

```bash
#!/usr/bin/env bash
# Smoke e2e de la demo (ejecutar tras `docker compose up -d` y esperar a que arranque).
set -euo pipefail

API="${API:-http://localhost:8080}"
AUTH="${AUTH:-http://localhost:8000}"
ANON="${ANON:?exporta ANON con la anon key de .env.docker}"
EMAIL="${DEMO_EMAIL:-demo@mnemo.local}"
PASS="${DEMO_PASSWORD:-mnemo-demo-1234}"

echo "1) health del backend"
curl -fsS "$API/v2/health" >/dev/null && echo "  ok"

echo "2) login del usuario demo"
TOKEN=$(curl -fsS "$AUTH/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
[ -n "$TOKEN" ] && echo "  token obtenido"

echo "3) endpoint autenticado /v2/orgs"
curl -fsS "$API/v2/orgs" -H "Authorization: Bearer $TOKEN" >/dev/null && echo "  ok (auth válida)"

echo "SMOKE OK"
```
Make it executable: `chmod +x scripts/smoke_demo.sh`.

- [ ] **Step 2: Write `docs/DEMO.md`:**

```markdown
# Demo on-prem de Mnemo (un comando)

Levanta Mnemo completo en local (Supabase self-hosted + Ollama + backend + frontend),
sin que ningún dato salga a la nube.

## Requisitos
- Docker + Docker Compose.
- **~15 GB de disco libre** (imágenes + modelo de Ollama ~5 GB + Postgres).

## Arranque
```bash
docker compose --env-file .env.docker up -d
# La primera vez: baja imágenes y, al usar la causa raíz, descarga el modelo.
docker compose exec ollama ollama pull deepseek-r1:8b   # ~5 GB (una vez)
```
Espera a que `backend` esté sano:
```bash
curl -fsS http://localhost:8080/v2/health
```

## Probar
1. Abre http://localhost:3000 y entra con **demo@mnemo.local** / **mnemo-demo-1234**.
2. En **Defect DNA** verás familias ya sembradas (un TimeoutException compartido entre
   `cliente-alpha` y `cliente-beta`). Abre una familia y pulsa **"Analizar causa raíz"**.
3. En **Assurance**, sube `examples/allure-ejemplo.json` o `examples/junit-ejemplo.xml` y
   mira el veredicto.

## Smoke automático
```bash
ANON=<anon key de .env.docker> ./scripts/smoke_demo.sh
```

## Apagar / limpiar
```bash
docker compose down            # conserva datos
docker compose down -v         # borra volúmenes (db + modelos)
```
```

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_demo.sh docs/DEMO.md
git commit -m "docs: smoke e2e + guía DEMO.md"
```

---

## Notas de implementación

- **Verificación**: Tasks 1-2 (build), 3/5 (config válida), 4 (pytest), 7-8 (parse). El arranque
  real del stack (Task 6 + el flujo e2e) **solo se valida con `docker compose up`**, que exige
  disco libre y no corre en CI. Si no puedes arrancar, deja los Dockerfiles/compose construidos
  y verificados por `build`/`config`, y marca el smoke e2e como pendiente de una máquina con espacio.
- **JWT**: el plan usa HS256 self-hosted (Task 4) — el camino cloud RS256/JWKS queda intacto
  (gated por `SUPABASE_JWT_SECRET`).
- **Imágenes**: las tags de Supabase/kong/ollama son orientativas del compose oficial; al primer
  `up` puede haber que ajustarlas a las que pullean/arrancan en el entorno (anótalo).
- **Disco**: liberar espacio ANTES de construir (la máquina está al límite).
```

