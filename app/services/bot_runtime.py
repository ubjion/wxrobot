"""微信机器人核心运行编排。"""

from __future__ import annotations

from typing import Any

from app.messages.reader import MessageEvent


class BotRuntime:
    """连接消息事件、AI 回复和人工确认队列。"""

    def __init__(self, reply_service: Any, approval_queue: Any, auto_send: bool = False) -> None:
        self.reply_service = reply_service
        self.approval_queue = approval_queue
        self.auto_send = auto_send

    def handle_event(self, event: MessageEvent) -> str | None:
        if event.message.get("sender_id") in (2, "2"):
            return None
        reply = self.reply_service.generate_reply(event)
        if reply is None:
            return None
        token = self.approval_queue.enqueue(event, reply)
        if self.auto_send:
            self.approval_queue.approve(token)
        return token
