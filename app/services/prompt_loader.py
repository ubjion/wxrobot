"""从本地 Markdown 文档加载 AI 系统提示词。"""

from __future__ import annotations

import os
from pathlib import Path


class PromptLoadError(RuntimeError):
    """提示词文档不可用。"""


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "assistant_system.md"


def load_system_prompt(path: str | os.PathLike[str] | None = None) -> str:
    configured = path or os.getenv("WX_BOT_PROMPT_FILE")
    prompt_path = Path(configured) if configured else DEFAULT_PROMPT_PATH
    if not prompt_path.exists():
        raise PromptLoadError(f"提示词文件不存在：{prompt_path}")
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptLoadError(f"提示词文件无法读取：{prompt_path}") from exc
    if not prompt:
        raise PromptLoadError(f"提示词文件为空：{prompt_path}")
    return prompt
