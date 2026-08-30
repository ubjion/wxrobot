"""微信机器人本地控制入口。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Iterable

from app.ai.deepseek import DeepSeekClient, DeepSeekConfig
from app.messages.reader import JsonWatermarkStore, MessageListener, MessageReader
from app.services.approval_queue import ApprovalQueue
from app.services.bot_runtime import BotRuntime
from app.services.reply_service import AiReplyService
from app.services.wechat_sender import WeChatSendError, WeChatUISender


def build_runtime(
    db: Any,
    users: Iterable[str],
    reply_service: Any,
    watermark_path: str | os.PathLike[str],
    send_func: Callable[..., Any] | None = None,
    interval: float = 1.0,
    auto_send: bool = False,
) -> tuple[MessageListener, ApprovalQueue]:
    reader = MessageReader(db, users=users)
    store = JsonWatermarkStore(watermark_path)
    sender = WeChatUISender(send_func=send_func, name_resolver=getattr(db, "get_nickname", None))
    queue = ApprovalQueue(sender)
    runtime = BotRuntime(reply_service, queue, auto_send=auto_send)
    listener = MessageListener(reader, store, runtime.handle_event, interval=interval)
    return listener, queue


def _default_watermark_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "wx-bot" / "watermarks.json"


def approve_for_console(queue: ApprovalQueue, token: str) -> str:
    try:
        return "已发送" if queue.approve(token) else "未找到该回复"
    except WeChatSendError as exc:
        return f"发送失败，回复仍保留：{exc}"


def main() -> None:
    from wechatauto import WeChatDB

    account = os.getenv("WECHAT_ACCOUNT") or None
    db = WeChatDB(account=account)
    users = [chat["username"] for chat in db.list_message_chats()]
    if not users:
        raise RuntimeError("未找到可监听的消息会话")
    config = DeepSeekConfig.from_env()
    ai_service = AiReplyService(DeepSeekClient(config))
    interval = float(os.getenv("WX_BOT_POLL_INTERVAL", "1.0"))
    send_mode = os.getenv("WX_BOT_SEND_MODE", "auto").strip().lower()
    if send_mode not in {"auto", "manual"}:
        raise ValueError("WX_BOT_SEND_MODE 必须是 auto 或 manual")
    listener, queue = build_runtime(
        db=db,
        users=users,
        reply_service=ai_service,
        watermark_path=os.getenv("WX_BOT_WATERMARK_FILE", str(_default_watermark_path())),
        interval=interval,
        auto_send=send_mode == "auto",
    )
    listener.start()
    print(f"微信机器人已启动（{send_mode} 模式）。输入 help 查看命令，输入 quit 退出。")
    try:
        while True:
            command = input("wx-bot> ").strip().split(maxsplit=1)
            if not command:
                continue
            if command[0] == "quit":
                break
            if command[0] == "help":
                print("list | approve <token> | reject <token> | quit")
            elif command[0] == "list":
                for pending in queue.list_pending():
                    print(f"{pending.token}: {pending.event.user} <- {pending.text}")
            elif command[0] == "approve" and len(command) == 2:
                print(approve_for_console(queue, command[1]))
            elif command[0] == "reject" and len(command) == 2:
                print("已丢弃" if queue.reject(command[1]) else "未找到该回复")
            else:
                print("未知命令，输入 help 查看用法")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
