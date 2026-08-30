"""微信机器人核心运行编排。"""

from __future__ import annotations

from typing import Any

from app.messages.reader import MessageEvent


class BotRuntime:
    """连接消息事件、AI 回复和人工确认队列。"""

    def __init__(self, reply_service: Any, approval_queue: Any) -> None:
        self.reply_service = reply_service
        self.approval_queue = approval_queue

    def handle_event(self, event: MessageEvent) -> str | None:
        reply = self.reply_service.generate_reply(event)
        if reply is None:
            return None
        return self.approval_queue.enqueue(event, reply)
