from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.paths import FRONTEND_DIR, FRONTEND_DIST
from app.routers import health, voice, describe, drawings

app = FastAPI(
    title="Voice2Canvas",
    description="语音绘图 Demo — FastAPI + ASR + LLM + Canvas",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(voice.router)
app.include_router(describe.router)
app.include_router(drawings.router)

# 静态前端：优先使用 frontend-react/dist，开启 html=True 以支持 /image.html 等路径
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend-dist")
elif FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
