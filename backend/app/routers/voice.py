import base64
import hashlib
import hmac
import json
import subprocess
import time
import uuid
import logging
from typing import Literal
from urllib.parse import urlencode

import websockets
import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.paths import PROMPTS_DIR
from app.services.llm import LLMError, chat_completion

router = APIRouter(prefix="/api/asr-nlu", tags=["voice"])
logger = logging.getLogger("asr")
logger.setLevel(logging.INFO)


class Stroke(BaseModel):
    color: str | None = Field(default=None)
    width: float | None = Field(default=None, ge=0)


class Size(BaseModel):
    width: float | None = Field(default=None, ge=0)
    height: float | None = Field(default=None, ge=0)
    relative: bool = True


class Position(BaseModel):
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    anchor: Literal[
        "top-left",
        "top",
        "top-right",
        "center-left",
        "center",
        "center-right",
        "bottom-left",
        "bottom",
        "bottom-right",
    ] | None = None


class Command(BaseModel):
    action: Literal["draw", "undo", "clear", "save"]
    shape: Literal["circle", "rect", "triangle", "line", "text", "free"] | None = None
    position: Position | None = None
    size: Size | None = None
    color: str | None = None
    stroke: Stroke | None = None
    fill: str | None = None
    text: str | None = None
    comment: str | None = None

    @field_validator("color", "fill")
    @classmethod
    def normalize_color(cls, v: str | None) -> str | None:
        if not v:
            return v
        return v.strip()


class VoiceResponse(BaseModel):
    commands: list[Command]
    reply_text: str
    asr_text: str


def load_prompt() -> str:
    prompt_path = PROMPTS_DIR / "voice_drawing.md"
    if not prompt_path.exists():
        return (
            "You are a voice drawing command parser. Return JSON only. "
            "If you fail, return empty array and brief reply."
        )
    return prompt_path.read_text(encoding="utf-8")


def clean_json_response(text: str) -> str:
    """
    去掉模型返回的 ```json ... ``` 包裹，提取纯 JSON 字符串。
    """
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


def transcode_to_pcm16k(raw_bytes: bytes) -> bytes:
    """
    使用系统 ffmpeg 将任意音频转为 16k 单声道 s16le PCM。
    需要本机已安装 ffmpeg。
    """
    try:
        ffmpeg_bin = settings.ffmpeg_bin or "ffmpeg"
        proc = subprocess.run(
            [
                ffmpeg_bin,
                "-i",
                "pipe:0",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-f",
                "s16le",
                "pipe:1",
            ],
            input=raw_bytes,
            capture_output=True,
            check=True,
        )
        return proc.stdout
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ffmpeg 转码失败: {exc}")


def _parse_app_id(app_id: str) -> str:
    # 示例项目会去掉前后空白并尝试转 int，这里保持兼容
    val = (app_id or "").strip()
    try:
        return str(int(val))
    except Exception:
        return val


def build_xfyun_url() -> str:
    # 讯飞听写新版 v2 域名
    host = "iat-api.xfyun.cn"
    path = "/v2/iat"
    date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(
        settings.xfyun_apisecret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{settings.xfyun_apikey}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    query = urlencode({"authorization": authorization, "date": date, "host": host})
    return f"wss://{host}{path}?{query}"


async def call_asr_xfyun(file: UploadFile) -> str:
    if not (settings.xfyun_appid and settings.xfyun_apikey and settings.xfyun_apisecret):
        raise HTTPException(status_code=400, detail="讯飞 ASR 未配置完成")

    raw_bytes = await file.read()
    pcm_bytes = transcode_to_pcm16k(raw_bytes)

    logger.info(f"xfyun start: pcm_len={len(pcm_bytes)}")
    url = build_xfyun_url()
    async with websockets.connect(url, ping_interval=None, max_size=4 * 1024 * 1024) as ws:
        final_text_parts: list[str] = []
        # send frames
        frame_size = 1280
        status = 0
        seq = 0
        for offset in range(0, len(pcm_bytes), frame_size):
            chunk = pcm_bytes[offset : offset + frame_size]
            if offset + frame_size >= len(pcm_bytes):
                status = 2
            audio_b64 = base64.b64encode(chunk).decode("utf-8")
            msg = {
                "header": {"app_id": settings.xfyun_appid, "status": status},
                "parameter": {
                    "iat": {
                        "domain": "iat",
                        "language": "zh_cn",
                        "accent": "mandarin",
                        "eos": 6000,
                        "dwa": "wpgs",
                        "result": {
                            "encoding": "utf8",
                            "compress": "raw",
                            "format": "json",
                        },
                    }
                },
                "payload": {
                    "audio": {
                        "encoding": "raw",
                        "sample_rate": 16000,
                        "channels": 1,
                        "bit_depth": 16,
                        "seq": seq,
                        "status": status,
                        "audio": audio_b64,
                    }
                },
            }
            seq += 1
            await ws.send(json.dumps(msg))
            if status == 2:
                break

        async for message in ws:
            data = json.loads(message)
            code = data.get("header", {}).get("code", 0)
            if code != 0:
                raise HTTPException(status_code=502, detail=f"讯飞 ASR 错误: {data}")
            payload = data.get("payload")
            if not payload:
                continue
            result = payload.get("result", {})
            text_b64 = result.get("text")
            if not text_b64:
                continue
            try:
                text_json = json.loads(base64.b64decode(text_b64))
                for seg in text_json.get("ws", []):
                    for cw in seg.get("cw", []):
                        w = cw.get("w")
                        if w:
                            final_text_parts.append(w)
                if text_json.get("ls"):
                    break
            except Exception:
                continue
        return "".join(final_text_parts).strip()


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


async def call_asr_baidu(file: UploadFile, *, language: str = "zh") -> str:
    if not (settings.baidu_api_key and settings.baidu_secret_key):
        raise HTTPException(status_code=400, detail="百度 ASR 未配置")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="未收到音频数据")
    pcm_bytes = transcode_to_pcm16k(raw_bytes)

    # 获取 access_token
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
    speech_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
    payload = {
        "format": "pcm",
        "rate": 16000,
        "channel": 1,
        "dev_pid": dev_pid,
        "token": access_token,
        "cuid": settings.baidu_cuid,
        "len": len(pcm_bytes),
        "speech": speech_b64,
    }
    logger.info(
        f"baidu rest start: len={len(pcm_bytes)}, dev_pid={dev_pid}, cuid={settings.baidu_cuid}"
    )

    asr_url = "http://vop.baidu.com/server_api"
    async with httpx.AsyncClient(timeout=settings.asr_timeout) as client:
        resp = await client.post(asr_url, json=payload, headers={"Content-Type": "application/json"})
    data = resp.json()
    if data.get("err_no") != 0:
        logger.error(f"baidu rest error: {data}")
        raise HTTPException(status_code=502, detail=f"百度 ASR 错误: {data}")

    result_list = data.get("result") or []
    text = "".join(result_list).strip() if isinstance(result_list, list) else str(result_list).strip()
    if not text:
        logger.warning(f"baidu rest empty result: {data}")
        raise HTTPException(status_code=400, detail="未识别到语音内容")
    logger.info(f"baidu rest result: {text}")
    return text


async def call_asr(file: UploadFile) -> str:
    vendor = getattr(settings, "asr_vendor", "baidu_rest").lower()
    if vendor in {"baidu", "baidu_rest"}:
        return await call_asr_baidu(file)
    if vendor == "xfyun":
        return await call_asr_xfyun(file)
    raise HTTPException(status_code=400, detail="未知 ASR_VENDOR")


async def call_nlu(asr_text: str) -> VoiceResponse:
    prompt = load_prompt()
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": asr_text},
    ]
    try:
        content = await chat_completion(
            messages,
            temperature=0.2,
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    cleaned = clean_json_response(content)
    try:
        data = VoiceResponse.model_validate_json(cleaned)
    except ValidationError as exc:
        logger.error(f"LLM JSON 解析失败，raw={content}")
        raise HTTPException(
            status_code=502, detail=f"LLM 输出不符合格式: {exc.errors()}"
        ) from exc
    return data


@router.post("")
async def asr_nlu(file: UploadFile = File(...)) -> VoiceResponse:
    """
    上传一段语音，返回命令列表 + 反馈文本。
    """
    if file.content_type and not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="请上传音频文件")

    asr_text = await call_asr(file)
    if not asr_text:
        raise HTTPException(status_code=400, detail="未识别到语音内容")

    nlu = await call_nlu(asr_text)
    nlu.asr_text = asr_text
    return nlu
