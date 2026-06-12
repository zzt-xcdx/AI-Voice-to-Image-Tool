"""快速测试 LLM 是否可用。用法: python scripts/test_llm.py"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.services.llm import LLMError, chat_completion  # noqa: E402


async def main() -> None:
    print("--- LLM Smoke Test ---")
    print(f"  base_url: {settings.llm_base_url}")
    print(f"  model:    {settings.llm_model}")
    if not settings.llm_api_key:
        print("  [FAIL] LLM_API_KEY 未配置")
        return

    try:
        reply = await chat_completion(
            [{"role": "user", "content": "请只回复 OK 两个字母。"}],
            max_tokens=10,
            temperature=0.0,
        )
        print(f"  [OK] {reply.strip()}")
    except LLMError as exc:
        print(f"  [FAIL] {exc}")
    except Exception as exc:  # 兜底其他异常
        print(f"  [FAIL] {type(exc).__name__}: {exc}")

print("LLM cfg", settings.llm_base_url, settings.llm_model)

if __name__ == "__main__":
    asyncio.run(main())
