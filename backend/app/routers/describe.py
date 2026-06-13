import base64
import json
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.paths import PROMPTS_DIR
from app.routers.voice import call_asr, clean_json_response
from app.services.llm import LLMError, chat_completion


router = APIRouter(prefix="/api/voice", tags=["voice"])


class ImagePromptOut(BaseModel):
    prompt_en: str = Field(..., min_length=3, description="Enhanced English prompt for image generation")
    prompt_cn: str | None = None
    style: str | None = None
    detail: str | None = None


class ChartSeries(BaseModel):
    name: str | None = None
    type: Literal["pie", "bar", "line"] | None = None
    data: list[float | int] = Field(default_factory=list)


class ChartSpec(BaseModel):
    type: Literal["pie", "bar", "line"]
    title: str | None = None
    labels: list[str] | None = None  # x 轴/类别
    series: list[ChartSeries] = Field(default_factory=list)
    note: str | None = None


class DescribeResponse(BaseModel):
    mode: Literal["image", "chart"]
    asr_text: str
    llm_text: str
    prompt_en: str | None = None
    chart: ChartSpec | None = None
    image_base64: str | None = None


def load_prompt(mode: Literal["image", "chart"]) -> str:
    prompt_path = PROMPTS_DIR / "voice_drawing.md"
    if not prompt_path.exists():
        return "You are a voice assistant. Return strict JSON."
    base = prompt_path.read_text(encoding="utf-8")
    # 在提示尾部追加模式指示，降低歧义
    extra = (
        "\n\n当前模式: IMAGE。输出示例: {\"prompt_en\": \"A cat on the moon\", \"prompt_cn\": \"...\"}"
        if mode == "image"
        else "\n\n当前模式: CHART。输出示例: {\"type\": \"pie\", \"title\": \"\", \"labels\": [\"A\",\"B\"], \"series\": [{\"name\":\"\", \"type\":\"pie\", \"data\":[60,40]}]}"
    )
    return base + extra


async def run_llm(asr_text: str, mode: Literal["image", "chart"]):
    prompt = load_prompt(mode)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps({"mode": mode, "text": asr_text}, ensure_ascii=False)},
    ]
    try:
        content = await chat_completion(messages, temperature=0.3)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    cleaned = clean_json_response(content)
    # 兼容模型返回以 "json" 开头的前缀
    cleaned = cleaned.strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].lstrip()
    try:
        if mode == "image":
            parsed = ImagePromptOut.model_validate_json(cleaned)
        else:
            parsed = ChartSpec.model_validate_json(cleaned)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"LLM 输出不符合格式: {exc.errors()}") from exc
    return content, parsed


async def call_qianfan_image(prompt_en: str) -> str:
    if not settings.image_api_key:
        raise HTTPException(status_code=400, detail="IMAGE_API_KEY 未配置")
    url = "https://qianfan.baidubce.com/v2/images/generations"
    payload = {
        "model": settings.image_model or "qwen-image",
        "prompt": prompt_en,
        "size": "1024x1024",
    }
    headers = {
        "Authorization": f"Bearer {settings.image_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.image_timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"图像生成失败: {resp.text}")
    data = resp.json()
    img_b64 = None
    if isinstance(data, dict):
        if isinstance(data.get("data"), list) and data["data"]:
            first = data["data"][0]
            img_b64 = first.get("b64_json") or first.get("b64")
            img_url = first.get("url")
            if not img_b64 and img_url:
                try:
                    async with httpx.AsyncClient(timeout=settings.image_timeout) as client:
                        img_resp = await client.get(img_url)
                        img_resp.raise_for_status()
                        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
                except Exception as exc:  # pragma: no cover - 网络异常兜底
                    raise HTTPException(status_code=502, detail=f"下载图像失败: {exc}") from exc
    if not img_b64:
        raise HTTPException(status_code=502, detail=f"图像生成响应缺少图片字段: {data}")
    return img_b64


@router.post("/describe", response_model=DescribeResponse)
async def describe(
    mode: Literal["image", "chart"] = Query(..., description="image | chart"),
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
) -> DescribeResponse:
    if not file and not text:
        raise HTTPException(status_code=400, detail="请上传音频或提供 text")
    if file and file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="请上传音频文件")

    if text:
        asr_text = text.strip()
    else:
        asr_text = await call_asr(file)  # type: ignore[arg-type]
        if not asr_text:
            raise HTTPException(status_code=400, detail="未识别到语音内容")

    llm_text, parsed = await run_llm(asr_text, mode)

    if mode == "image":
        prompt_en = parsed.prompt_en  # type: ignore[attr-defined]
        img_b64 = await call_qianfan_image(prompt_en)
        # 自动保存到画板库（存为背景，命令为空）
        try:
            payload = {
                "title": parsed.prompt_cn or "AI图片",  # type: ignore[attr-defined]
                "commands": [],
                "asr_text": asr_text,
                "reply_text": prompt_en,
                "background_base64": f"data:image/png;base64,{img_b64}",
            }
            # 延迟导入以避免循环
            from app.routers import drawings as drawings_router

            # 同步插入数据库
            await drawings_router.create_drawing_from_payload(payload)
        except Exception:
            # 自动保存失败不影响主流程
            pass

        return DescribeResponse(
            mode="image",
            asr_text=asr_text,
            llm_text=llm_text,
            prompt_en=prompt_en,
            image_base64=img_b64,
        )

    # chart 模式
    return DescribeResponse(
        mode="chart",
        asr_text=asr_text,
        llm_text=llm_text,
        chart=parsed,  # type: ignore[arg-type]
    )
