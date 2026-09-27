"""微信机器人本地控制入口。"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Callable, Iterable

from app.ai.deepseek import DeepSeekClient, DeepSeekConfig
from app.messages.reader import JsonWatermarkStore, MessageListener, MessageReader
from app.services.approval_queue import ApprovalQueue
from app.services.bot_runtime import BotRuntime
from app.services.context_store import JsonContextStore
from app.services.group_summary import GroupSummaryService
from app.services.knowledge_base import KnowledgeBase
from app.services.reply_service import AiReplyService
from app.services.scheduler import JsonScheduleStore, MessageScheduler
from app.services.weather import OpenMeteoWeatherClient
from app.services.web_search import FirecrawlSearchClient
from app.services.wechat_sender import WeChatSendError, WeChatUISender


def build_runtime(
    db: Any,
    users: Iterable[str],
    reply_service: Any,
    watermark_path: str | os.PathLike[str],
    send_func: Callable[..., Any] | None = None,
    interval: float = 1.0,
    auto_send: bool = False,
    bot_names: set[str] | None = None,
    group_summary_service: Any | None = None,
    user_provider: Any | None = None,
    user_refresh_interval: float = 30.0,
) -> tuple[MessageListener, ApprovalQueue]:
    reader = MessageReader(
        db,
        users=users,
        user_provider=user_provider,
        user_refresh_interval=user_refresh_interval,
    )
    store = JsonWatermarkStore(watermark_path)
    sender = WeChatUISender(send_func=send_func, name_resolver=getattr(db, "get_nickname", None))
    queue = ApprovalQueue(sender)
    runtime = BotRuntime(
        reply_service,
        queue,
        auto_send=auto_send,
        bot_names=bot_names,
        fallback_reply=os.getenv(
            "WX_BOT_FALLBACK_REPLY",
            "我收到啦，但 AI 服务暂时不可用，请稍后再试。",
        ),
        group_summary_service=group_summary_service,
    )
    listener = MessageListener(
        reader,
        store,
        runtime.handle_event,
        interval=interval,
        error_handler=lambda event: print(
            f"消息处理失败，将自动重试（会话：{event.user}）"
        ),
    )
    return listener, queue


def _default_watermark_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "wx-bot" / "watermarks.json"


def get_bot_names(self_info: dict, group_names: str = "") -> set[str]:
    names = {
        value.strip()
        for value in (
            self_info.get("nick_name"),
            self_info.get("remark"),
            self_info.get("username"),
        )
        if isinstance(value, str) and value.strip()
    }
    names.update(name.strip() for name in group_names.split(",") if name.strip())
    return names


def get_listening_users(db: Any) -> list[str]:
    session_users = [chat["username"] for chat in db.get_sessions(limit=100)]
    message_users = [chat["username"] for chat in db.list_message_chats()]
    ignored_users = {"newsapp", "filehelper", "weixin", "fmessage", "floatbottle"}
    return list(dict.fromkeys(
        user for user in session_users + message_users if user not in ignored_users
    ))


def approve_for_console(queue: ApprovalQueue, token: str) -> str:
    try:
        return "已发送" if queue.approve(token) else "未找到该回复"
    except WeChatSendError as exc:
        return f"发送失败，回复仍保留：{exc}"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
    )
    from wechatauto import WeChatDB

    account = os.getenv("WECHAT_ACCOUNT") or None
    db = WeChatDB(account=account)
    self_info = db.get_self_info()
    bot_names = get_bot_names(self_info, os.getenv("WX_BOT_GROUP_NAMES", ""))
    users = get_listening_users(db)
    if not users:
        raise RuntimeError("未找到可监听的消息会话")
    config = DeepSeekConfig.from_env()
    context_path = os.getenv(
        "WX_BOT_CONTEXT_FILE",
        str(_default_watermark_path().with_name("contexts.json")),
    )
    context_limit = int(os.getenv("WX_BOT_CONTEXT_MESSAGES", "20"))
    context_store = JsonContextStore(context_path, max_messages=context_limit)
    ai_client = DeepSeekClient(config)
    knowledge_dir = Path(os.getenv("WX_BOT_KNOWLEDGE_DIR", str(Path.cwd() / "knowledge")))
    knowledge_db = Path(os.getenv("WX_BOT_KNOWLEDGE_DB", str(_default_watermark_path().with_name("knowledge.sqlite"))))
    knowledge_base = KnowledgeBase(knowledge_db)
    if knowledge_dir.exists():
        knowledge_base.sync_directory(knowledge_dir)
    ai_service = AiReplyService(
        ai_client,
        context_store=context_store,
        weather_client=OpenMeteoWeatherClient(),
        search_client=FirecrawlSearchClient(),
        bot_names=bot_names,
        knowledge_base=knowledge_base,
    )
    summary_service = GroupSummaryService(
        db,
        ai_client,
        max_messages=int(os.getenv("WX_BOT_SUMMARY_MESSAGES", "50")),
    )
    interval = float(os.getenv("WX_BOT_POLL_INTERVAL", "1.0"))
    user_refresh_interval = float(
        os.getenv("WX_BOT_USER_REFRESH_INTERVAL", "30.0")
    )
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
        bot_names=bot_names,
        group_summary_service=summary_service,
        user_provider=lambda: get_listening_users(db),
        user_refresh_interval=user_refresh_interval,
    )
    schedule_path = os.getenv(
        "WX_BOT_SCHEDULE_FILE",
        str(_default_watermark_path().with_name("schedules.json")),
    )
    scheduler = MessageScheduler(
        queue.sender,
        store=JsonScheduleStore(schedule_path),
    )
    listener.callback.__self__.scheduler = scheduler
    listener.start()
    scheduler.start(interval=1.0)
    print(f"微信机器人已启动（{send_mode} 模式）。输入 help 查看命令，输入 quit 退出。")
    try:
        while True:
            command = input("wx-bot> ").strip().split(maxsplit=1)
            if not command:
                continue
            if command[0] == "quit":
                break
            if command[0] == "help":
                print("list | schedule once <user> <ISO时间> <内容> | schedule every <user> <秒数> <内容> | schedules | cancel <任务ID> | quit")
            elif command[0] == "list":
                for pending in queue.list_pending():
                    print(f"{pending.token}: {pending.event.user} <- {pending.text}")
            elif command[0] == "approve" and len(command) == 2:
                print(approve_for_console(queue, command[1]))
            elif command[0] == "reject" and len(command) == 2:
                print("已丢弃" if queue.reject(command[1]) else "未找到该回复")
            elif command[0] == "schedules":
                for item in scheduler.list_schedules():
                    kind = f"every {item.interval_seconds}s" if item.interval_seconds else "once"
                    print(f"{item.id}: {kind} {item.user_id} @ {item.next_run} <- {item.text}")
            elif command[0] == "cancel" and len(command) == 2:
                print("已取消" if scheduler.cancel(command[1]) else "未找到该任务")
            elif command[0] == "schedule" and len(command) == 2:
                try:
                    parts = command[1].split(maxsplit=3)
                    if parts[0] == "once" and len(parts) == 4:
                        from datetime import datetime
                        task_id = scheduler.add_once(parts[1], parts[3], datetime.fromisoformat(parts[2]))
                    elif parts[0] == "every" and len(parts) == 4:
                        task_id = scheduler.add_interval(parts[1], parts[3], int(parts[2]))
                    else:
                        raise ValueError
                    print(f"已创建任务：{task_id}")
                except (ValueError, IndexError):
                    print("格式错误：schedule once <用户ID> <ISO时间> <内容> 或 schedule every <用户ID> <秒数> <内容>")
            else:
                print("未知命令，输入 help 查看用法")
    finally:
        scheduler.stop()
        listener.stop()


if __name__ == "__main__":
    main()
