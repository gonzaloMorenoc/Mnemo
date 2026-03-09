import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Model Settings
MODEL_NAME = "deepseek-r1:8b"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Upgraded from all-MiniLM-L6-v2 (384 dims) to bge-base-en-v1.5 (768 dims) for
# significantly better retrieval precision on technical/code content.
# IMPORTANT: delete db_chroma/ before first run after this change to avoid
# dimension mismatch errors with the existing vector store.
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

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
