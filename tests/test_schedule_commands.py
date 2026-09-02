from datetime import datetime, timezone

import pytest

from app.messages.reader import MessageEvent
from app.services.bot_runtime import BotRuntime, parse_schedule_command
from app.services.scheduler import MessageScheduler


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue(self, event, text):
        self.calls.append((event, text))
        return "reply-confirmation"


class FakeReplyService:
    def generate_reply(self, event):
        raise AssertionError("schedule commands must not call AI")


class FakeSender:
    def send(self, user, text):
        return True


def test_user_can_create_one_time_task_for_self():
    scheduler = MessageScheduler(FakeSender())
    queue = FakeQueue()
    runtime = BotRuntime(FakeReplyService(), queue, scheduler=scheduler)
    event = MessageEvent(
        user="alice",
        message={
            "type": "文本",
            "content": "/定时 2030-01-01T08:00:00+00:00 开会提醒",
        },
    )

    token = runtime.handle_event(event)

    assert token == "reply-confirmation"
    task = scheduler.list_schedules()[0]
    assert task.user_id == "alice"
    assert task.next_run == "2030-01-01T08:00:00+00:00"
    assert task.text == "开会提醒"
    assert "定时任务已创建" in queue.calls[0][1]


def test_user_can_create_recurring_task_for_self():
    scheduler = MessageScheduler(FakeSender())
    queue = FakeQueue()
    runtime = BotRuntime(FakeReplyService(), queue, scheduler=scheduler)
    event = MessageEvent(
        user="alice",
        message={"type": "文本", "content": "/每 3600 喝水提醒"},
    )

    runtime.handle_event(event)

    task = scheduler.list_schedules()[0]
    assert task.user_id == "alice"
    assert task.interval_seconds == 3600
    assert task.text == "喝水提醒"


def test_non_command_still_uses_ai():
    class ReplyService:
        def generate_reply(self, event):
            return "普通回复"

    scheduler = MessageScheduler(FakeSender())
    queue = FakeQueue()
    runtime = BotRuntime(ReplyService(), queue, scheduler=scheduler)

    runtime.handle_event(
        MessageEvent(user="alice", message={"type": "文本", "content": "你好"})
    )

    assert len(queue.calls) == 1
    assert scheduler.list_schedules() == []


@pytest.mark.parametrize(
    "content",
    ["/每 abc 你好", "/每 -1 你好", "/定时 not-a-time 你好", "/定时"],
)
def test_malformed_schedule_command_returns_one_format_error(content):
    scheduler = MessageScheduler(FakeSender())
    queue = FakeQueue()
    runtime = BotRuntime(FakeReplyService(), queue, scheduler=scheduler)

    token = runtime.handle_event(
        MessageEvent(user="alice", message={"type": "文本", "content": content})
    )

    assert token == "reply-confirmation"
    assert len(queue.calls) == 1
    assert "格式错误" in queue.calls[0][1]
    assert scheduler.list_schedules() == []


def test_parse_compact_clock_command_without_space():
    command = parse_schedule_command(
        "/定时 21:40发送你好",
        now=datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc),
    )

    assert command[0] == "once"
    assert command[1] == datetime(2030, 1, 1, 21, 40, tzinfo=timezone.utc)
    assert command[2] == "发送你好"


def test_parse_clock_command_with_space():
    command = parse_schedule_command(
        "/定时 21:40 发送你好",
        now=datetime(2030, 1, 1, 22, 0, tzinfo=timezone.utc),
    )

    assert command[1] == datetime(2030, 1, 2, 21, 40, tzinfo=timezone.utc)
    assert command[2] == "发送你好"
