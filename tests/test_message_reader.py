import logging
import threading
import time

from app.messages.reader import JsonWatermarkStore, MessageListener, MessageReader


class FakeDB:
    def __init__(self, messages_by_user):
        self.messages_by_user = messages_by_user
        self.calls = []

    def get_new_messages(self, user, since_seq):
        self.calls.append((user, since_seq))
        return [
            message
            for message in self.messages_by_user.get(user, [])
            if message["sort_seq"] > since_seq
        ]


def test_poll_once_emits_messages_and_ack_advances_user_watermark():
    db = FakeDB(
        {
            "alice": [
                {"local_id": 1, "sort_seq": 10, "content": "one"},
                {"local_id": 2, "sort_seq": 12, "content": "two"},
            ]
        }
    )
    reader = MessageReader(db, users=["alice"])

    events = reader.poll_once()

    assert [event.message["local_id"] for event in events] == [1, 2]
    assert reader.watermarks == {}
    for event in events:
        reader.ack(event)
    assert reader.watermarks == {"alice": 12}
    assert db.calls == [("alice", 0)]


def test_ack_prevents_database_overlap_from_replaying_message():
    db = FakeDB(
        {
            "alice": [
                {"local_id": 1, "sort_seq": 10, "content": "one"},
            ]
        }
    )
    reader = MessageReader(db, users=["alice"])

    first = reader.poll_once()
    reader.ack(first[0])
    second = reader.poll_once()

    assert len(first) == 1
    assert second == []
    assert reader.watermarks == {"alice": 10}


def test_poll_once_keeps_watermark_when_database_read_fails():
    class FailingDB:
        def get_new_messages(self, user, since_seq):
            raise RuntimeError("database unavailable")

    reader = MessageReader(FailingDB(), users=["alice"], watermarks={"alice": 7})

    events = reader.poll_once()

    assert events == []
    assert reader.watermarks == {"alice": 7}


def test_poll_requires_explicit_ack_before_advancing_watermark():
    db = FakeDB({"alice": [{"local_id": 1, "sort_seq": 10, "content": "one"}]})
    reader = MessageReader(db, users=["alice"])

    event = reader.poll_once()[0]

    assert reader.watermarks == {}
    reader.ack(event)
    assert reader.watermarks == {"alice": 10}


def test_listener_failure_does_not_ack_later_users_in_same_poll(tmp_path):
    db = FakeDB({
        "alice": [{"local_id": 1, "sort_seq": 10, "content": "fail"}],
        "bob": [{"local_id": 2, "sort_seq": 20, "content": "must retry"}],
    })
    reader = MessageReader(db, users=["alice", "bob"])
    store = JsonWatermarkStore(tmp_path / "watermarks.json")
    listener = None

    def fail_first(event):
        listener._stop_event.set()
        raise RuntimeError("callback failed")

    listener = MessageListener(reader, store, fail_first, interval=0.01)
    listener._run()

    assert store.load().get("bob", 0) == 0
    assert [event.user for event in reader.poll_once()] == ["alice", "bob"]


def test_listener_logs_callback_failure_without_raw_message(caplog, tmp_path):
    caplog.set_level(logging.WARNING, logger="wx-bot")
    db = FakeDB({
        "wxid_private123": [
            {"local_id": 1, "sort_seq": 10, "content": "不能写入日志的正文"}
        ]
    })
    reader = MessageReader(db, users=["wxid_private123"])
    store = JsonWatermarkStore(tmp_path / "watermarks.json")
    listener = None

    def fail(event):
        listener._stop_event.set()
        raise LookupError("private failure detail")

    listener = MessageListener(reader, store, fail, interval=0.01)
    listener._run()

    assert "LookupError" in caplog.text
    assert "wxid_private123" not in caplog.text
    assert "不能写入日志的正文" not in caplog.text
    assert "private failure detail" not in caplog.text


def test_poll_once_discovers_new_user_without_replaying_history():
    class DynamicDB(FakeDB):
        def get_messages(self, user, limit):
            return [{"local_id": 99, "sort_seq": 100, "content": "历史消息"}]

    users = ["alice"]

    def discover_users():
        return users

    db = DynamicDB({"alice": []})
    reader = MessageReader(db, users=[], user_provider=discover_users)

    first = reader.poll_once()
    users.append("new-group@chatroom")
    db.messages_by_user["new-group@chatroom"] = [
        {"local_id": 99, "sort_seq": 100, "content": "历史消息"},
        {"local_id": 100, "sort_seq": 101, "content": "新消息"},
    ]
    second = reader.poll_once()

    assert first == []
    assert [event.message["sort_seq"] for event in second] == [101]
    assert "new-group@chatroom" in reader.users


def test_seed_missing_watermarks_skips_history_on_first_start():
    class HistoricalDB(FakeDB):
        def get_messages(self, user, limit):
            return [{"local_id": 9, "sort_seq": 100, "content": "历史消息"}]

    db = HistoricalDB({"alice": [{"local_id": 10, "sort_seq": 101, "content": "新消息"}]})
    reader = MessageReader(db, users=["alice"])

    reader.seed_missing_watermarks()

    assert reader.watermarks == {"alice": 100}
    assert [event.message["sort_seq"] for event in reader.poll_once()] == [101]


def test_listener_resets_existing_watermark_to_latest_on_restart(tmp_path):
    class HistoricalDB(FakeDB):
        def get_messages(self, user, limit):
            return [{"local_id": 9, "sort_seq": 100, "content": "最新历史消息"}]

    store = JsonWatermarkStore(tmp_path / "watermarks.json")
    store.save({"alice": 50})
    reader = MessageReader(HistoricalDB({"alice": []}), users=["alice"])

    MessageListener(reader, store, lambda event: None)

    assert reader.watermarks == {"alice": 100}
    assert store.load() == {"alice": 100}


def test_rewind_event_allows_failed_message_to_be_retried():
    db = FakeDB({"alice": [{"local_id": 1, "sort_seq": 10, "content": "重试"}]})
    reader = MessageReader(db, users=["alice"])
    event = reader.poll_once()[0]

    reader.rewind_event(event)

    retried = reader.poll_once()
    assert [item.message["sort_seq"] for item in retried] == [10]


def test_watermark_store_round_trips_values(tmp_path):
    path = tmp_path / "watermarks.json"
    store = JsonWatermarkStore(path)

    store.save({"alice": 12, "room": 34})

    assert store.load() == {"alice": 12, "room": 34}


def test_listener_persists_watermarks_and_delivers_events(tmp_path):
    db = FakeDB({"alice": [{"local_id": 1, "sort_seq": 10, "content": "one"}]})
    reader = MessageReader(db, users=["alice"])
    store = JsonWatermarkStore(tmp_path / "watermarks.json")
    received = []
    listener = MessageListener(reader, store, received.append, interval=0.01)

    listener.start()
    deadline = time.monotonic() + 1
    while not received and time.monotonic() < deadline:
        time.sleep(0.01)
    listener.stop()

    assert len(received) == 1
    assert store.load() == {"alice": 10}
    assert listener.is_running is False


def test_listener_stop_is_safe_before_start(tmp_path):
    reader = MessageReader(FakeDB({}), users=[])
    listener = MessageListener(
        reader,
        JsonWatermarkStore(tmp_path / "watermarks.json"),
        lambda event: None,
    )

    listener.stop()

    assert listener.is_running is False
