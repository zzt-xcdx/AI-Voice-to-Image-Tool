"""快速验证 API 配置。用法: python scripts/test_apis.py"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.services.llm import LLMError, chat_completion  # noqa: E402


async def test_llm() -> None:
    print("--- LLM ---")
    print(f"  base_url: {settings.llm_base_url}")
    print(f"  model:    {settings.llm_model}")
    if not settings.llm_api_key:
        print("  [SKIP] LLM_API_KEY 未配置")
        return
    try:
        reply = await chat_completion(
            [{"role": "user", "content": "回复 OK 两个字母即可。"}],
            max_tokens=10,
        )
        print(f"  [OK] {reply.strip()[:80]}")
    except LLMError as exc:
        print(f"  [FAIL] {exc}")


async def main() -> None:
    await test_llm()
    print("\n完成。若 LLM 为 OK，脚手架即可用于开发。")


if __name__ == "__main__":
    asyncio.run(main())
