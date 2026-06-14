import base64
import logging

import httpx
from fastapi import HTTPException, UploadFile

from app.config import settings

logger = logging.getLogger("asr")


def clean_json_response(text: str) -> str:
    """去掉模型返回的 ```json ... ``` 包裹，提取纯 JSON 字符串。"""
    t = text.strip()
    if t.startswith("```"):
        parts = t.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("{") and part.endswith("}"):
                return part
        if len(parts) >= 2:
            return parts[1].strip()
    return t


def resolve_baidu_dev_pid(language: str, configured: str) -> int:
    val = (configured or "").strip().lower()
    if val and val != "auto":
        try:
            return int(val)
        except Exception:
            pass
    lang = (language or "").lower()
    if lang in {"en", "en-us", "en-gb", "english"}:
        return 17372
    if lang in {"yue", "ct", "cantonese", "sc", "sichuan", "sichuanese"}:
        return 15376
    return 15372


def _detect_audio_format(raw_bytes: bytes) -> tuple[str, int]:
    if len(raw_bytes) >= 4 and raw_bytes[:4] == b"RIFF":
        return "wav", 16000
    raise HTTPException(
        status_code=400,
        detail="不支持的音频格式，请使用 16kHz WAV（浏览器会自动转换）",
    )


async def call_asr_baidu(file: UploadFile, *, language: str = "zh") -> str:
    if not (settings.baidu_api_key and settings.baidu_secret_key):
        raise HTTPException(status_code=400, detail="百度 ASR 未配置")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="未收到音频数据")

    audio_format, sample_rate = _detect_audio_format(raw_bytes)

    token_url = (
        "https://aip.baidubce.com/oauth/2.0/token"
        f"?grant_type=client_credentials&client_id={settings.baidu_api_key}"
        f"&client_secret={settings.baidu_secret_key}"
    )
    async with httpx.AsyncClient(timeout=settings.asr_timeout) as client:
        token_resp = await client.post(token_url)
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        logger.error(f"baidu token error: {token_data}")
        raise HTTPException(status_code=502, detail=f"获取百度token失败: {token_data}")

    dev_pid = resolve_baidu_dev_pid(language, settings.baidu_dev_pid)
    speech_b64 = base64.b64encode(raw_bytes).decode("utf-8")
    payload = {
        "format": audio_format,
        "rate": sample_rate,
        "channel": 1,
        "dev_pid": dev_pid,
        "token": access_token,
        "cuid": settings.baidu_cuid,
        "len": len(raw_bytes),
        "speech": speech_b64,
    }
    logger.info(
        f"baidu asr start: len={len(raw_bytes)}, format={audio_format}, dev_pid={dev_pid}"
    )

    asr_url = "http://vop.baidu.com/server_api"
    async with httpx.AsyncClient(timeout=settings.asr_timeout) as client:
        resp = await client.post(asr_url, json=payload, headers={"Content-Type": "application/json"})
    data = resp.json()
    if data.get("err_no") != 0:
        logger.error(f"baidu asr error: {data}")
        raise HTTPException(status_code=502, detail=f"百度 ASR 错误: {data}")

    result_list = data.get("result") or []
    text = "".join(result_list).strip() if isinstance(result_list, list) else str(result_list).strip()
    if not text:
        logger.warning(f"baidu asr empty result: {data}")
        raise HTTPException(status_code=400, detail="未识别到语音内容")
    logger.info(f"baidu asr result: {text}")
    return text


async def call_asr(file: UploadFile) -> str:
    return await call_asr_baidu(file)
