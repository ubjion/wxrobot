import pytest

from app.messages.reader import MessageEvent
from app.services.approval_queue import ApprovalQueue, PendingReply
from app.services.wechat_sender import WeChatUISender


class FakeSender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send(self, user, text):
        self.calls.append((user, text))
        if self.error:
            raise self.error


def make_event():
    return MessageEvent(user="alice", message={"type": "文本", "content": "你好"})


def test_enqueue_and_approve_sends_reply_once():
    sender = FakeSender()
    queue = ApprovalQueue(sender)
    token = queue.enqueue(make_event(), "你好，我是助手")

    pending = queue.list_pending()
    result = queue.approve(token)

    assert isinstance(pending[0], PendingReply)
    assert result is True
    assert sender.calls == [("alice", "你好，我是助手")]
    assert queue.list_pending() == []


def test_reject_removes_reply_without_sending():
    sender = FakeSender()
    queue = ApprovalQueue(sender)
    token = queue.enqueue(make_event(), "不发送")

    assert queue.reject(token) is True
    assert queue.list_pending() == []
    assert sender.calls == []


def test_failed_send_keeps_reply_for_manual_retry():
    sender = FakeSender(error=RuntimeError("send failed"))
    queue = ApprovalQueue(sender)
    token = queue.enqueue(make_event(), "稍后重试")

    with pytest.raises(RuntimeError, match="send failed"):
        queue.approve(token)

    assert len(queue.list_pending()) == 1


def test_wechat_sender_passes_text_to_reference_ui_adapter():
    calls = []

    def fake_quick_send(text, who, verify):
        calls.append((text, who, verify))
        return True

    sender = WeChatUISender(send_func=fake_quick_send)

    result = sender.send("alice", "回复内容")

    assert result is True
    assert calls == [("回复内容", "alice", True)]
