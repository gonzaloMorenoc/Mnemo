import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Model Settings (el modelo LLM por defecto por proveedor vive en src/llm/factory.py)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# LLM provider intercambiable (ollama local | openai-compatible | anthropic)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
ALLOW_EXTERNAL_LLM = os.getenv("ALLOW_EXTERNAL_LLM", "").lower() == "true"

# Jira/Confluence Search Paths (Optional)
JIRA_URL = os.getenv("JIRA_URL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")

CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")

# Multi-tenant KB (Postgres + Supabase). Defaults vacios = modo single-tenant.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Supabase auth (verificacion JWT via JWKS)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "")
# HS256 shared secret for self-hosted GoTrue (docker demo). Empty = cloud RS256 path.
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# CI webhook (Mnemo Autopilot) — ingesta viva desde el CI del cliente.
# Secreto compartido para verificar la firma HMAC-SHA256 del webhook.
CI_WEBHOOK_SECRET = os.getenv("CI_WEBHOOK_SECRET", "")
# Cuenta de servicio (miembro del org) a la que se atribuye la ingesta del CI.
CI_SERVICE_USER_ID = os.getenv("CI_SERVICE_USER_ID", "")
# Límite de tamaño del cuerpo del webhook de CI (anti-DoS). Por defecto 10 MiB.
CI_MAX_BODY_BYTES = int(os.getenv("CI_MAX_BODY_BYTES", str(10 * 1024 * 1024)))
# Límite de tamaño de las subidas de archivo (reportes/HU). Por defecto 10 MiB.
INGEST_MAX_BYTES = int(os.getenv("INGEST_MAX_BYTES", str(10 * 1024 * 1024)))
# Org único al que está ligada la cuenta de servicio del CI. Si se define, el webhook
# rechaza (403) cualquier artefacto con otro org_id (aislamiento mono-org).
CI_SERVICE_ORG_ID = os.getenv("CI_SERVICE_ORG_ID", "")

# Triaje (Mnemo Autopilot F2): nº mínimo de fallos con firma de infra en un run
# para considerarlo "co-fallo masivo" (señal de problema de entorno, no de producto).
TRIAGE_MASS_COFAILURE_MIN = int(os.getenv("TRIAGE_MASS_COFAILURE_MIN", "3"))

# GitHub App (F3c): credenciales globales de la app.
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY", "")

# Certificación (Mnemo Autopilot F4a): firma Ed25519 de Release Assurance Certificates.
MNEMO_VERSION = "0.4.0"
MNEMO_SIGNING_PRIVATE_KEY = os.getenv("MNEMO_SIGNING_PRIVATE_KEY", "")
MNEMO_SIGNING_PUBLIC_KEY = os.getenv("MNEMO_SIGNING_PUBLIC_KEY", "")


def multi_tenant_enabled() -> bool:
    """True solo si hay BD Postgres y Supabase configurados."""
    return bool(DATABASE_URL and SUPABASE_URL)
