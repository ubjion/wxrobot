"""微信 UI 发送适配器。"""

from __future__ import annotations

from typing import Any, Callable


class WeChatUISender:
    """使用参考项目的 GUI 发送能力发送文本。"""

    def __init__(self, send_func: Callable[..., Any] | None = None) -> None:
        self._send_func = send_func or self._load_reference_sender()

    @staticmethod
    def _load_reference_sender() -> Callable[..., Any]:
        try:
            from wechatauto.guia import quick_send
        except ImportError as exc:
            raise RuntimeError("未安装或无法加载 wechatauto 的 UI 发送模块") from exc
        return quick_send

    def send(self, user: str, text: str) -> Any:
        if not user:
            raise ValueError("user 不能为空")
        if not text.strip():
            raise ValueError("text 不能为空")
        return self._send_func(text, user, verify=True)
