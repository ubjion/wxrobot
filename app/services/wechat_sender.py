"""微信 UI 发送适配器。"""

from __future__ import annotations

from collections import OrderedDict
import logging
import threading
import time
from typing import Any, Callable


logger = logging.getLogger("wx-bot")


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
        reply_func: Callable[..., Any] | None = None,
        gui_factory: Callable[[], Any] | None = None,
        name_cache_ttl: float = 600.0,
        name_cache_size: int = 512,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if name_cache_ttl <= 0:
            raise ValueError("name_cache_ttl must be positive")
        if name_cache_size <= 0:
            raise ValueError("name_cache_size must be positive")
        self._name_resolver = name_resolver
        self._gui_factory = gui_factory
        self._gui = None
        self._ui_lock = threading.RLock()
        self._using_reference_sender = send_func is None
        self._send_func = send_func
        self._reply_func = reply_func
        self._name_cache_ttl = float(name_cache_ttl)
        self._name_cache_size = int(name_cache_size)
        self._clock = clock
        self._name_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def _get_gui(self) -> Any:
        with self._ui_lock:
            if self._gui is not None:
                checker = getattr(self._gui, "is_alive", None)
                if callable(checker):
                    try:
                        if not checker():
                            self._gui = None
                    except Exception:
                        self._gui = None
            if self._gui is None:
                if self._gui_factory is None:
                    from wechatauto.guia import WeChatGUI
                    self._gui_factory = WeChatGUI
                self._gui = self._gui_factory()
            return self._gui

    def _load_reference_sender(self) -> Callable[..., Any]:
        try:
            from wechatauto.guia import WeChatGUI
        except ImportError as exc:
            raise RuntimeError("未安装或无法加载 wechatauto 的 UI 发送模块") from exc

        def send(text: str, who: str, verify: bool) -> Any:
            gui = self._get_gui()
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

    def _load_reference_reply(self) -> Callable[..., Any]:
        try:
            from wechatauto.guia import WeChatGUI
        except ImportError as exc:
            raise RuntimeError("未安装或无法加载 wechatauto 的引用回复模块") from exc

        def reply(text: str, who: str, verify: bool) -> Any:
            gui = self._get_gui()
            target = self._resolve_name(who)
            if target != getattr(gui, "_current_chat", None):
                if not gui.open_chat(target):
                    return False
            return gui.reply_msg(text, None, verify=verify)

        return reply

    def _resolve_name(self, user: str) -> str:
        if self._name_resolver is None:
            return user
        now = self._clock()
        with self._ui_lock:
            cached = self._name_cache.get(user)
            if cached is not None:
                created_at, name = cached
                if now - created_at < self._name_cache_ttl:
                    self._name_cache.move_to_end(user)
                    return name
                self._name_cache.pop(user, None)
            try:
                name = self._name_resolver(user)
            except Exception:
                return user
            resolved = name.strip() if isinstance(name, str) and name.strip() else user
            if resolved != user:
                self._name_cache[user] = (now, resolved)
                self._name_cache.move_to_end(user)
                while len(self._name_cache) > self._name_cache_size:
                    self._name_cache.popitem(last=False)
            return resolved

    def send(self, user: str, text: str) -> Any:
        if not user:
            raise ValueError("user 不能为空")
        if not text.strip():
            raise ValueError("text 不能为空")
        target = user if self._using_reference_sender else self._resolve_name(user)
        send_func = self._send_func or self._load_reference_sender()
        started = time.perf_counter()
        with self._ui_lock:
            result = send_func(text, target, verify=True)
        logger.info("微信普通发送耗时 %.2f 秒，成功=%s", time.perf_counter() - started, bool(result))
        if not result:
            message = getattr(result, "get", lambda key, default=None: default)(
                "message", "微信发送未确认"
            )
            raise WeChatSendError(str(message or "微信发送未确认"))
        return result

    def reply(self, user: str, text: str) -> Any:
        if not user:
            raise ValueError("user 不能为空")
        if not text.strip():
            raise ValueError("text 不能为空")
        target = self._resolve_name(user)
        reply_func = self._reply_func or self._load_reference_reply()
        started = time.perf_counter()
        with self._ui_lock:
            result = reply_func(text, target, verify=True)
        logger.info("微信引用回复耗时 %.2f 秒，成功=%s", time.perf_counter() - started, bool(result))
        if not result:
            message = getattr(result, "get", lambda key, default=None: default)(
                "message", "微信引用回复未确认"
            )
            message = str(message or "微信引用回复未确认")
            if "已操作发送" not in message:
                return self.send(user, text)
            raise WeChatSendError(message)
        return result
