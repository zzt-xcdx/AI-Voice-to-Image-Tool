import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings


class LLMError(Exception):
    pass


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY 未配置，请复制 .env.example 为 .env 并填写")

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if response_format is not None:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        response = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code != 200:
        raise LLMError(f"LLM 请求失败 ({response.status_code}): {response.text}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"LLM 响应格式异常: {data}") from exc


async def chat_completion_stream(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    if not settings.llm_api_key:
        raise LLMError("LLM_API_KEY 未配置，请复制 .env.example 为 .env 并填写")

    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        async with client.stream(
            "POST",
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise LLMError(
                    f"LLM 流式请求失败 ({response.status_code}): {body.decode()}"
                )

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                chunk = line[6:]
                if chunk.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                    delta = data["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
