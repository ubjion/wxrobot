"""将消息事件转换为 AI 回复。"""

from __future__ import annotations

from typing import Any

from app.messages.reader import MessageEvent


class AiReplyService:
    """只生成回复文本，不负责向微信发送。"""

    _TEXT_TYPES = {1, "文本", "text"}

    def __init__(self, ai_client: Any, system_prompt: str = "你是一个简洁、可靠的微信助手。") -> None:
        if not system_prompt.strip():
            raise ValueError("system_prompt 不能为空")
        self.ai_client = ai_client
        self.system_prompt = system_prompt

    def generate_reply(self, event: MessageEvent) -> str | None:
        message_type = event.message.get("type")
        content = event.message.get("content")
        if message_type not in self._TEXT_TYPES or not isinstance(content, str):
            return None
        content = content.strip()
        if not content:
            return None
        return self.ai_client.complete([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": content},
        ])
