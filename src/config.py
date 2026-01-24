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
