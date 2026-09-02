"""按用户 ID 隔离保存最近对话上下文。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Dict, List, Mapping

from app.services.privacy import redact_sensitive_text


class JsonContextStore:
    """使用 JSON 文件持久化各用户最近的 user/assistant 消息。"""

    def __init__(
        self,
        path: str | os.PathLike[str],
        max_messages: int = 20,
        redactor: Callable[[str], str] = redact_sensitive_text,
    ) -> None:
        if max_messages <= 0:
            raise ValueError("max_messages must be positive")
        self.path = Path(path)
        self.max_messages = max_messages
        self.redactor = redactor

    def load(self) -> Dict[str, List[dict[str, str]]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            str(user_id): [
                {"role": item["role"], "content": item["content"]}
                for item in messages
                if isinstance(item, dict)
                and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str)
            ][-self.max_messages:]
            for user_id, messages in raw.items()
            if isinstance(messages, list)
        }

    def get_messages(self, user_id: str) -> List[dict[str, str]]:
        return list(self.load().get(user_id, []))

    def append_exchange(self, user_id: str, user_content: str, assistant_content: str) -> None:
        if not user_id:
            raise ValueError("user_id 不能为空")
        if not user_content.strip() or not assistant_content.strip():
            raise ValueError("对话内容不能为空")
        data = self.load()
        messages = data.setdefault(user_id, [])
        messages.extend([
            {"role": "user", "content": self.redactor(user_content)},
            {"role": "assistant", "content": self.redactor(assistant_content)},
        ])
        data[user_id] = messages[-self.max_messages:]
        self._save(data)

    def clear(self, user_id: str) -> None:
        data = self.load()
        data.pop(user_id, None)
        self._save(data)

    def _save(self, data: Mapping[str, List[dict[str, str]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
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
