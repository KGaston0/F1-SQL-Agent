"""Configuración central: rutas y parámetros leídos de variables de entorno (.env)."""
import os
from pathlib import Path

try:  # python-dotenv es opcional para poder ejecutar los scripts de BD sin el resto del stack
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = ROOT / os.getenv("DB_PATH", "data/db/f1.db")
RAW_DIR = ROOT / os.getenv("RAW_DIR", "data/raw/jolpica")  # caché de respuestas de la API
VECTORSTORE_DIR = ROOT / os.getenv("VECTORSTORE_DIR", "data/vectorstore")
PDF_DIR = ROOT / os.getenv("PDF_DIR", "data/pdfs")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

SCHEMA_PATH = ROOT / "src" / "database" / "schema.sql"
JOLPICA_BASE_URL = os.getenv("JOLPICA_BASE_URL", "https://api.jolpi.ca/ergast/f1")

# Límites de seguridad para la herramienta SQL del agente
SQL_MAX_ROWS = int(os.getenv("SQL_MAX_ROWS", "200"))
SQL_TIMEOUT_S = float(os.getenv("SQL_TIMEOUT_S", "5"))
