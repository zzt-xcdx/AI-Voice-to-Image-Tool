from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_DIST = ROOT_DIR / "frontend-react" / "dist"
DATA_DIR = ROOT_DIR / "data"
SQLITE_DB = DATA_DIR / "drawings.db"
PROMPTS_DIR = ROOT_DIR / "prompts"
ENV_FILE = ROOT_DIR / ".env"
