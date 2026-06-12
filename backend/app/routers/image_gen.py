import base64
import sqlite3
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.paths import SQLITE_DB, DATA_DIR


router = APIRouter(prefix="/api/gen-image", tags=["image"])


def _ensure_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generated_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT,
            model TEXT,
            image_base64 TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


_ensure_db()


class ImageGenReq(BaseModel):
    prompt: str = Field(..., description="生成描述")
    size: str | None = Field(default=None, description="分辨率，如 768x768，可选")
    model: str | None = Field(default=None, description="模型名，可覆盖默认")


class ImageGenResp(BaseModel):
    prompt: str
    model: str
    image_base64: str
    id: int


def _save_image(prompt: str, model: str, b64: str) -> int:
    conn = sqlite3.connect(SQLITE_DB)
    try:
        cur = conn.execute(
            "INSERT INTO generated_images (prompt, model, image_base64) VALUES (?, ?, ?)",
            (prompt, model, b64),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@router.post("", response_model=ImageGenResp)
async def gen_image(body: ImageGenReq) -> ImageGenResp:
    if not settings.image_api_key:
        raise HTTPException(status_code=400, detail="IMAGE_API_KEY 未配置")
    model = body.model or settings.image_model or "qwen-image"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": body.prompt,
    }
    if body.size:
        payload["size"] = body.size
    url = "https://qianfan.baidubce.com/v2/images/generations"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.image_api_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.image_timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except Exception as exc:  # network layer
        raise HTTPException(status_code=502, detail=f"调用绘图接口失败: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    images = data.get("data") or data.get("result") or []
    if not images:
        raise HTTPException(status_code=502, detail=f"绘图接口返回空: {data}")
    # 兼容 data[0].b64_image/base64/url
    first = images[0]
    b64 = first.get("b64_image") or first.get("base64") or first.get("image") or first.get("img")
    url = first.get("url")
    if not b64 and url:
        # 拉取 URL 并转为 base64
        try:
            async with httpx.AsyncClient(timeout=settings.image_timeout) as client:
                r2 = await client.get(url)
            if r2.status_code != 200:
                raise HTTPException(status_code=502, detail=f"下载图片失败: {r2.status_code}")
            b64 = base64.b64encode(r2.content).decode("utf-8")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"下载图片异常: {exc}") from exc
    if not b64:
        raise HTTPException(status_code=502, detail=f"未找到返回的图片字段: {first}")
    # 验证一下 base64
    try:
        base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=502, detail="图片 base64 解析失败")

    new_id = _save_image(body.prompt, model, b64)
    return ImageGenResp(prompt=body.prompt, model=model, image_base64=b64, id=new_id)
