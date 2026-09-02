"""微信机器人核心运行编排。"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any

from app.messages.reader import MessageEvent


class BotRuntime:
    """连接消息事件、AI 回复和人工确认队列。"""

    def __init__(
        self,
        reply_service: Any,
        approval_queue: Any,
        auto_send: bool = False,
        scheduler: Any | None = None,
        bot_names: set[str] | None = None,
        fallback_reply: str = "我收到啦，但 AI 服务暂时不可用，请稍后再试。",
        group_summary_service: Any | None = None,
    ) -> None:
        self.reply_service = reply_service
        self.approval_queue = approval_queue
        self.auto_send = auto_send
        self.scheduler = scheduler
        self.bot_names = {name.strip() for name in (bot_names or set()) if name.strip()}
        self.fallback_reply = fallback_reply
        self.group_summary_service = group_summary_service

    def handle_event(self, event: MessageEvent) -> str | None:
        if event.message.get("sender_id") in (2, "2"):
            return None
        content = event.message.get("content")
        if event.user.endswith("@chatroom") and not self._mentions_bot(content):
            return None
        if isinstance(content, str) and content.strip() == "/清除上下文":
            cleared = self.reply_service.clear_context(event.user)
            message = "已清除你的对话上下文。" if cleared else "当前未启用对话上下文。"
            return self._enqueue_or_send(event, message)
        try:
            command = parse_schedule_command(content)
        except (ValueError, TypeError, OverflowError):
            return self._enqueue_or_send(
                event,
                "格式错误：/定时 <ISO时间> <内容> 或 /每 <秒数> <内容>",
            )
        if command is not None and self.scheduler is not None:
            try:
                kind, value, text = command
                if kind == "once":
                    task_id = self.scheduler.add_once(event.user, text, value)
                else:
                    task_id = self.scheduler.add_interval(event.user, text, value)
                return self._enqueue_or_send(
                    event, f"定时任务已创建：{task_id}"
                )
            except ValueError:
                return self._enqueue_or_send(
                    event,
                    "格式错误：/定时 <ISO时间> <内容> 或 /每 <秒数> <内容>",
                )
        if (
            event.user.endswith("@chatroom")
            and self.group_summary_service is not None
            and self._is_summary_request(content)
        ):
            try:
                return self._enqueue_or_send(
                    event, self.group_summary_service.summarize(event.user)
                )
            except Exception:
                return self._enqueue_or_send(event, self.fallback_reply)
        try:
            reply = self.reply_service.generate_reply(event)
        except Exception:
            reply = self.fallback_reply
        if reply is None:
            return None
        return self._enqueue_or_send(event, reply)

    def _mentions_bot(self, content: Any) -> bool:
        if not isinstance(content, str):
            return False
        return "@我" in content or any(f"@{name}" in content for name in self.bot_names)

    @staticmethod
    def _is_summary_request(content: Any) -> bool:
        if not isinstance(content, str):
            return False
        return any(word in content for word in ("总结群聊", "总结一下群聊", "总结最近群聊", "群聊总结"))

    def _enqueue_or_send(self, event: MessageEvent, text: str) -> str:
        token = self.approval_queue.enqueue(event, text)
        if self.auto_send:
            self.approval_queue.approve(token)
        return token


def parse_schedule_command(content: Any, now: datetime | None = None):
    if not isinstance(content, str):
        return None
    parts = content.strip().split(maxsplit=2)
    if not parts or parts[0] not in {"/定时", "/每"}:
        return None
    if parts[0] == "/定时":
        if len(parts) < 2:
            raise ValueError("invalid schedule command")
        clock = re.match(r"^(\d{1,2}):(\d{2})(.*)$", parts[1])
        if clock:
            hour, minute = int(clock.group(1)), int(clock.group(2))
            text = (clock.group(3) if len(parts) == 2 else parts[2]).strip()
            if hour > 23 or minute > 59 or not text:
                raise ValueError("invalid clock schedule")
            current = now or datetime.now().astimezone()
            run_at = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_at <= current:
                run_at += timedelta(days=1)
            return "once", run_at, text
        if len(parts) != 3 or not parts[2].strip():
            raise ValueError("invalid schedule command")
        return "once", datetime.fromisoformat(parts[1]), parts[2].strip()
    if len(parts) != 3 or not parts[2].strip():
        raise ValueError("invalid schedule command")
    interval = int(parts[1])
    if interval <= 0:
        raise ValueError("interval must be positive")
    return "every", interval, parts[2].strip()
