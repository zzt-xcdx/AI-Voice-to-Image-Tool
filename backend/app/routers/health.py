from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm_configured": bool(settings.llm_api_key),
        "model": settings.llm_model,
    }
