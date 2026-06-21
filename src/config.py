import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Model Settings
MODEL_NAME = "deepseek-r1:8b"
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

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "logs")
DB_PATH = os.path.join(BASE_DIR, "db_chroma")
CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")

# Chunking Settings
CHUNK_SIZE = 2500
CHUNK_OVERLAP = 500

# Jira/Confluence Search Paths (Optional)
JIRA_URL = os.getenv("JIRA_URL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")

CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")

# Multi-tenant KB (Postgres + Supabase). Defaults vacios = modo single-tenant.
DATABASE_URL = os.getenv("DATABASE_URL", "")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "data", "uploads"))
_raw_top_k = os.getenv("DEFAULT_TOP_K", "8")
try:
    DEFAULT_TOP_K = int(_raw_top_k)
except ValueError as exc:
    raise ValueError(f"DEFAULT_TOP_K must be an integer, got: {_raw_top_k!r}") from exc

# Supabase auth (verificacion JWT via JWKS)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "")


def multi_tenant_enabled() -> bool:
    """True solo si hay BD Postgres y Supabase configurados."""
    return bool(DATABASE_URL and SUPABASE_URL)
