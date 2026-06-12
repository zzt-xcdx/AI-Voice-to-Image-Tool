from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.paths import FRONTEND_DIST
from app.routers import health, voice, drawings, background, image_gen

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
app.include_router(drawings.router)
app.include_router(background.router)
app.include_router(image_gen.router)

if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/")
async def index():
    if FRONTEND_DIST.exists():
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
    return JSONResponse({"message": "前端未构建，请运行 npm run build 或使用 npm run dev (5173)。"}, status_code=404)
