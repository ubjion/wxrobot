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


def test_poll_once_emits_messages_and_advances_each_user_watermark():
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
    assert reader.watermarks == {"alice": 12}
    assert db.calls == [("alice", 0)]


def test_poll_once_deduplicates_messages_when_database_returns_overlap():
    db = FakeDB(
        {
            "alice": [
                {"local_id": 1, "sort_seq": 10, "content": "one"},
            ]
        }
    )
    reader = MessageReader(db, users=["alice"])

    first = reader.poll_once()
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
