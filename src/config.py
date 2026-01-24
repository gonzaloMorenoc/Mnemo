import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Model Settings
MODEL_NAME = "deepseek-r1:8b"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "logs")
DB_PATH = os.path.join(BASE_DIR, "db_chroma")

# Chunking Settings
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Jira/Confluence Search Paths (Optional)
JIRA_URL = os.getenv("JIRA_URL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")

CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME")
