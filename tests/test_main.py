from app.main import build_runtime


class FakeDB:
    def get_new_messages(self, user, since_seq):
        return []


class FakeAI:
    def generate_reply(self, event):
        return "回复"


def test_build_runtime_wires_reading_ai_approval_and_sending(tmp_path):
    listener, queue = build_runtime(
        db=FakeDB(),
        users=["alice"],
        reply_service=FakeAI(),
        watermark_path=tmp_path / "watermarks.json",
        send_func=lambda text, who, verify: True,
    )

    assert listener.reader.users == ("alice",)
    assert listener.callback.__self__.reply_service is not None
    assert queue.list_pending() == []
