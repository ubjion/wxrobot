"""微信 UI 发送适配器。"""

from __future__ import annotations

from typing import Any, Callable


def screen_has_content(image: Any) -> bool:
    """判断截图是否包含桌面内容，兼容微信深色主题。"""
    width, height = image.size
    total = non_background = 0
    pixels = image.load()
    for y in range(0, height, 16):
        for x in range(0, width, 16):
            red, green, blue = pixels[x, y][:3]
            total += 1
            if max(red, green, blue) > 30:
                non_background += 1
    return non_background / max(total, 1) > 0.05


class WeChatSendError(RuntimeError):
    """微信 UI 未确认消息发送成功。"""


class WeChatUISender:
    """使用参考项目的 GUI 发送能力发送文本。"""

    def __init__(self, send_func: Callable[..., Any] | None = None) -> None:
        self._send_func = send_func or self._load_reference_sender()

    @staticmethod
    def _load_reference_sender() -> Callable[..., Any]:
        try:
            from wechatauto.guia import WeChatGUI
        except ImportError as exc:
            raise RuntimeError("未安装或无法加载 wechatauto 的 UI 发送模块") from exc

        def send(text: str, who: str, verify: bool) -> Any:
            gui = WeChatGUI()
            gui.desktop_available = lambda: (
                gui.is_alive()
                and screen_has_content(gui._grab_screen(gui.render_rect))
            )
            return gui.send_msg(text, who, verify)

        return send

    def send(self, user: str, text: str) -> Any:
        if not user:
            raise ValueError("user 不能为空")
        if not text.strip():
            raise ValueError("text 不能为空")
        result = self._send_func(text, user, verify=True)
        if not result:
            message = getattr(result, "get", lambda key, default=None: default)(
                "message", "微信发送未确认"
            )
            raise WeChatSendError(str(message or "微信发送未确认"))
        return result
