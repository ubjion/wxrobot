from datetime import datetime, timedelta, timezone

import pytest
import time

from app.services.scheduler import JsonScheduleStore, MessageScheduler, ScheduledMessage


class FakeSender:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def send(self, user, text):
        self.calls.append((user, text))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_schedule_store_round_trips_schedules(tmp_path):
    path = tmp_path / "schedules.json"
    store = JsonScheduleStore(path)
    schedule = ScheduledMessage(
        id="morning",
        user_id="alice",
        text="早上好",
        next_run="2030-01-01T08:00:00+00:00",
    )

    store.save([schedule])

    assert store.load() == [schedule]


def test_scheduler_sends_due_one_time_message_and_removes_it():
    sender = FakeSender()
    now = datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)
    scheduler = MessageScheduler(sender, clock=lambda: now)
    scheduler.add_once("alice", "提醒内容", now)

    sent = scheduler.run_once()

    assert sent == 1
    assert sender.calls == [("alice", "提醒内容")]
    assert scheduler.list_schedules() == []


def test_scheduler_advances_recurring_message_after_send():
    sender = FakeSender()
    now = datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)
    scheduler = MessageScheduler(sender, clock=lambda: now)
    scheduler.add_interval("alice", "定时内容", interval_seconds=3600, start_at=now)

    assert scheduler.run_once() == 1
    schedule = scheduler.list_schedules()[0]

    assert schedule.next_run == "2030-01-01T09:00:00+00:00"


def test_scheduler_keeps_failed_message_for_retry():
    sender = FakeSender(RuntimeError("send failed"))
    now = datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)
    scheduler = MessageScheduler(sender, clock=lambda: now)
    scheduler.add_once("alice", "重试内容", now)

    assert scheduler.run_once() == 0
    assert len(scheduler.list_schedules()) == 1


def test_scheduler_rejects_empty_or_invalid_schedule_values():
    scheduler = MessageScheduler(FakeSender())

    with pytest.raises(ValueError):
        scheduler.add_once("", "内容", datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        scheduler.add_interval("alice", "内容", interval_seconds=0)


def test_scheduler_background_thread_sends_due_task_and_stops(tmp_path):
    sender = FakeSender()
    now = datetime.now(timezone.utc)
    scheduler = MessageScheduler(
        sender,
        store=JsonScheduleStore(tmp_path / "schedules.json"),
        clock=lambda: now,
    )
    scheduler.add_once("alice", "后台任务", now)

    scheduler.start(interval=0.01)
    deadline = time.monotonic() + 1
    while not sender.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    scheduler.stop()

    assert sender.calls == [("alice", "后台任务")]
    assert scheduler.is_running is False
