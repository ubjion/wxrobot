from app.main import build_runtime
from app.main import approve_for_console
from app.services.wechat_sender import WeChatSendError


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


def test_approve_for_console_keeps_running_when_ui_send_fails():
    class FailingQueue:
        def approve(self, token):
            raise WeChatSendError("微信窗口不可见")

    result = approve_for_console(FailingQueue(), "reply-1")

    assert result.startswith("发送失败，回复仍保留")
