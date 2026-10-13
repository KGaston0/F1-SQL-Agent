"""Central configuration: paths and parameters read from environment variables (.env)."""
import os
from pathlib import Path

try:  # python-dotenv is optional so the DB scripts can run without the rest of the stack
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / os.getenv("DB_PATH", "data/db/f1.db")
RAW_DIR = ROOT / os.getenv("RAW_DIR", "data/raw/jolpica")  # cache of API responses
VECTORSTORE_DIR = ROOT / os.getenv("VECTORSTORE_DIR", "data/vectorstore")
PDF_DIR = ROOT / os.getenv("PDF_DIR", "data/pdfs")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # "gemini" | "groq"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low")  # "" = model default; lower = faster
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Agent
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))  # max LLM <-> tool rounds per question
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))  # retries on 429/5xx from the LLM provider
LOG_PATH = ROOT / os.getenv("LOG_PATH", "data/logs/agent.jsonl")

SCHEMA_PATH = ROOT / "src" / "database" / "schema.sql"
JOLPICA_BASE_URL = os.getenv("JOLPICA_BASE_URL", "https://api.jolpi.ca/ergast/f1")

# Safety limits for the agent's SQL tool
SQL_MAX_ROWS = int(os.getenv("SQL_MAX_ROWS", "200"))
SQL_TIMEOUT_S = float(os.getenv("SQL_TIMEOUT_S", "5"))
