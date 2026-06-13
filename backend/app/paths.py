from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_REACT_DIR = ROOT_DIR / "frontend-react"
FRONTEND_DIST = FRONTEND_REACT_DIR / "dist"
PROMPTS_DIR = ROOT_DIR / "prompts"
ENV_FILE = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
