"""按用户 ID 定时发送主动消息。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Callable, List
from uuid import uuid4


@dataclass(frozen=True)
class ScheduledMessage:
    id: str
    user_id: str
    text: str
    next_run: str
    interval_seconds: int | None = None


class JsonScheduleStore:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> List[ScheduledMessage]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        schedules = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                schedule = ScheduledMessage(
                    id=str(item["id"]),
                    user_id=str(item["user_id"]),
                    text=str(item["text"]),
                    next_run=str(item["next_run"]),
                    interval_seconds=item.get("interval_seconds"),
                )
                _validate_schedule(schedule)
                schedules.append(schedule)
            except (KeyError, TypeError, ValueError):
                continue
        return schedules

    def save(self, schedules: List[ScheduledMessage]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(item) for item in schedules], ensure_ascii=False, indent=2)
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


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _validate_schedule(schedule: ScheduledMessage) -> None:
    if not schedule.id or not schedule.user_id or not schedule.text.strip():
        raise ValueError("任务 ID、用户 ID 和消息内容不能为空")
    _parse_time(schedule.next_run)
    if schedule.interval_seconds is not None and schedule.interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")


class MessageScheduler:
    def __init__(
        self,
        sender,
        store: JsonScheduleStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.sender = sender
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._schedules = store.load() if store else []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        for schedule in self._schedules:
            _validate_schedule(schedule)

    def add_once(self, user_id: str, text: str, run_at: datetime) -> str:
        return self._add(user_id, text, run_at, None)

    def add_interval(
        self,
        user_id: str,
        text: str,
        interval_seconds: int,
        start_at: datetime | None = None,
    ) -> str:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        return self._add(user_id, text, start_at or self.clock(), interval_seconds)

    def _add(
        self,
        user_id: str,
        text: str,
        run_at: datetime,
        interval_seconds: int | None,
    ) -> str:
        schedule = ScheduledMessage(
            id=f"schedule-{uuid4().hex[:12]}",
            user_id=user_id,
            text=text,
            next_run=run_at.isoformat(),
            interval_seconds=interval_seconds,
        )
        _validate_schedule(schedule)
        self._schedules.append(schedule)
        self._save()
        return schedule.id

    def list_schedules(self) -> List[ScheduledMessage]:
        return list(self._schedules)

    def cancel(self, schedule_id: str) -> bool:
        old_size = len(self._schedules)
        self._schedules = [item for item in self._schedules if item.id != schedule_id]
        if len(self._schedules) != old_size:
            self._save()
            return True
        return False

    def run_once(self) -> int:
        now = self.clock()
        sent = 0
        remaining: List[ScheduledMessage] = []
        for schedule in self._schedules:
            if _parse_time(schedule.next_run) > now:
                remaining.append(schedule)
                continue
            try:
                result = self.sender.send(schedule.user_id, schedule.text)
                if result is False:
                    raise RuntimeError("scheduled send failed")
            except Exception:
                remaining.append(schedule)
                continue
            sent += 1
            if schedule.interval_seconds is not None:
                next_run = _parse_time(schedule.next_run)
                step = timedelta(seconds=schedule.interval_seconds)
                while next_run <= now:
                    next_run += step
                remaining.append(replace(schedule, next_run=next_run.isoformat()))
        self._schedules = remaining
        self._save()
        return sent

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, interval: float = 1.0) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(interval,),
            name="message-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None

    def _run(self, interval: float) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(interval)

    def _save(self) -> None:
        if self.store:
            self.store.save(self._schedules)
