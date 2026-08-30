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

    def __init__(
        self,
        send_func: Callable[..., Any] | None = None,
        name_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self._name_resolver = name_resolver
        self._using_reference_sender = send_func is None
        self._send_func = send_func or self._load_reference_sender()

    def _load_reference_sender(self) -> Callable[..., Any]:
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
            target = self._resolve_name(who)
            if target != who:
                if not gui.open_chat(target):
                    return False
                result = gui.send_msg(text, None, False)
                if verify and result and not gui._verify_sent(text, who):
                    from wechatauto.param import WxResponse
                    return WxResponse.failure(
                        "消息已操作发送，但数据库未确认", data={"content": text}
                    )
                return result
            return gui.send_msg(text, who, verify)

        return send

    def _resolve_name(self, user: str) -> str:
        if self._name_resolver is None:
            return user
        try:
            name = self._name_resolver(user)
        except Exception:
            return user
        return name.strip() if isinstance(name, str) and name.strip() else user

    def send(self, user: str, text: str) -> Any:
        if not user:
            raise ValueError("user 不能为空")
        if not text.strip():
            raise ValueError("text 不能为空")
        target = user if self._using_reference_sender else self._resolve_name(user)
        result = self._send_func(text, target, verify=True)
        if not result:
            message = getattr(result, "get", lambda key, default=None: default)(
                "message", "微信发送未确认"
            )
            raise WeChatSendError(str(message or "微信发送未确认"))
        return result
