"""只读消息轮询与去重。"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Tuple


@dataclass(frozen=True)
class MessageEvent:
    """一条从指定会话读取到的新消息。"""

    user: str
    message: Mapping[str, Any]


class MessageReader:
    """基于 WeChatDB.get_new_messages 的只读消息读取器。"""

    def __init__(
        self,
        db: Any,
        users: Iterable[str],
        watermarks: MutableMapping[str, int] | None = None,
        user_provider: Any | None = None,
    ) -> None:
        self.db = db
        self.users = tuple(dict.fromkeys(users))
        self.watermarks: Dict[str, int] = dict(watermarks or {})
        self.user_provider = user_provider

    def poll_once(self) -> List[MessageEvent]:
        """读取所有监听会话的新消息；单个会话失败不会推进其游标。"""
        self.refresh_users()
        events: List[MessageEvent] = []
        for user in self.users:
            since_seq = self.watermarks.get(user, 0)
            try:
                messages = self.db.get_new_messages(user, since_seq) or []
            except Exception:
                continue

            ordered = sorted(messages, key=lambda item: item.get("sort_seq", 0))
            seen_in_poll: set[Tuple[str, str, Any]] = set()
            for message in ordered:
                sort_seq = message.get("sort_seq", 0)
                if sort_seq <= since_seq:
                    continue
                identity = self._identity(user, message)
                if identity in seen_in_poll:
                    continue
                seen_in_poll.add(identity)
                events.append(MessageEvent(user=user, message=message))
        return events

    def ack(self, event: MessageEvent) -> None:
        """仅在消息处理成功后推进对应会话的游标。"""
        sort_seq = int(event.message.get("sort_seq", 0))
        if sort_seq <= 0:
            return
        self.watermarks[event.user] = max(
            self.watermarks.get(event.user, 0), sort_seq
        )

    def refresh_users(self) -> None:
        if self.user_provider is None:
            return
        try:
            discovered = tuple(dict.fromkeys(self.user_provider()))
        except Exception:
            return
        self.users = tuple(dict.fromkeys((*self.users, *discovered)))
        self.seed_missing_watermarks(discovered)

    def seed_missing_watermarks(self, users: Iterable[str] | None = None) -> None:
        for user in users or self.users:
            if user in self.watermarks:
                continue
            try:
                latest = self.db.get_messages(user, limit=1) or []
                if latest:
                    self.watermarks[user] = max(
                        int(item.get("sort_seq", 0)) for item in latest
                    )
            except Exception:
                continue

    def reset_watermarks_to_latest(self, users: Iterable[str] | None = None) -> None:
        for user in users or self.users:
            try:
                latest = self.db.get_messages(user, limit=1) or []
                if latest:
                    self.watermarks[user] = max(
                        int(item.get("sort_seq", 0)) for item in latest
                    )
            except Exception:
                continue

    def rewind_event(self, event: MessageEvent) -> None:
        sort_seq = int(event.message.get("sort_seq", 0))
        if sort_seq <= 0 or event.user not in self.watermarks:
            return
        current = self.watermarks[event.user]
        self.watermarks[event.user] = min(current, sort_seq - 1)

    @staticmethod
    def _identity(user: str, message: Mapping[str, Any]) -> Tuple[str, str, Any]:
        server_id = message.get("server_id")
        if server_id not in (None, ""):
            return user, "server_id", server_id
        return user, "local_id", (
            message.get("local_id"),
            message.get("sort_seq"),
        )


class JsonWatermarkStore:
    """将会话游标以 JSON 文件持久化。"""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(user): int(seq)
            for user, seq in data.items()
            if isinstance(seq, int) and seq >= 0
        }

    def save(self, watermarks: Mapping[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(dict(watermarks), ensure_ascii=False, indent=2)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp:
                temp.write(payload)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


class MessageListener:
    """在后台线程中轮询 MessageReader 并持久化游标。"""

    def __init__(
        self,
        reader: MessageReader,
        store: JsonWatermarkStore,
        callback: Any,
        interval: float = 1.0,
        error_handler: Any | None = None,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.reader = reader
        self.store = store
        self.callback = callback
        self.interval = interval
        self.error_handler = error_handler
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.reader.watermarks.update(self.store.load())
        self.reader.reset_watermarks_to_latest()
        self.store.save(self.reader.watermarks)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="message-listener",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            events = self.reader.poll_once()
            for event in events:
                try:
                    self.callback(event)
                except Exception:
                    self.reader.rewind_event(event)
                    if self.error_handler is not None:
                        try:
                            self.error_handler(event)
                        except Exception:
                            pass
                    break
                self.reader.ack(event)
                self.store.save(self.reader.watermarks)
            self.store.save(self.reader.watermarks)
            self._stop_event.wait(self.interval)
