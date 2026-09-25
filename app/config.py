import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

APP_PORT = int(os.getenv("APP_PORT", "8766"))
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
LANGUAGETOOL_URL = os.getenv("LANGUAGETOOL_URL", "http://127.0.0.1:8010")
LANGUAGETOOL_TIMEOUT_SECONDS = float(os.getenv("LANGUAGETOOL_TIMEOUT_SECONDS", "60"))
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "nl-NL")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
TEMP_FILE_TTL_MINUTES = int(os.getenv("TEMP_FILE_TTL_MINUTES", "60"))
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "storage/uploads")
TEMP_DIR = BASE_DIR / os.getenv("TEMP_DIR", "storage/temporary")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ALLOWED_EXTENSIONS = {ext.lower().strip() for ext in os.getenv("ALLOWED_EXTENSIONS", ".txt,.docx,.pdf").split(",") if ext.strip()}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
