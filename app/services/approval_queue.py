"""人工确认后再发送微信回复。"""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any, Dict, List

from app.messages.reader import MessageEvent


@dataclass(frozen=True)
class PendingReply:
    token: str
    event: MessageEvent
    text: str


class ApprovalQueue:
    """保存待人工确认的回复，并委托 sender 执行实际发送。"""

    def __init__(self, sender: Any) -> None:
        self.sender = sender
        self._pending: Dict[str, PendingReply] = {}
        self._next_token = 1
        self._lock = threading.RLock()

    def enqueue(self, event: MessageEvent, text: str) -> str:
        if not text.strip():
            raise ValueError("reply text 不能为空")
        with self._lock:
            token = f"reply-{self._next_token}"
            self._next_token += 1
            self._pending[token] = PendingReply(token, event, text)
            return token

    def list_pending(self) -> List[PendingReply]:
        with self._lock:
            return list(self._pending.values())

    def approve(self, token: str) -> bool:
        with self._lock:
            pending = self._pending.get(token)
            if pending is None:
                return False
            self.sender.send(pending.event.user, pending.text)
            del self._pending[token]
            return True

    def reject(self, token: str) -> bool:
        with self._lock:
            if token not in self._pending:
                return False
            del self._pending[token]
            return True
