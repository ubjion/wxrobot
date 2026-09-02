import pytest

from app.messages.reader import MessageEvent
from app.services.approval_queue import ApprovalQueue, PendingReply
from app.services.wechat_sender import (
    WeChatSendError,
    WeChatUISender,
    screen_has_content,
)


class FakeSender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send(self, user, text):
        self.calls.append((user, text))
        if self.error:
            raise self.error

    def reply(self, user, text):
        self.calls.append(("reply", user, text))
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


def test_approve_unknown_token_returns_false_without_crashing():
    queue = ApprovalQueue(FakeSender())

    assert queue.approve("reply-missing") is False


def test_wechat_sender_treats_failure_response_as_send_failure():
    class FailureResponse(dict):
        def __bool__(self):
            return False

    sender = WeChatUISender(send_func=lambda text, who, verify: FailureResponse())

    with pytest.raises(WeChatSendError, match="未确认"):
        sender.send("alice", "回复内容")


def test_dark_theme_window_counts_as_visible_content():
    class FakeImage:
        size = (32, 32)

        def load(self):
            return self

        def __getitem__(self, position):
            return (220, 220, 220) if position == (0, 0) else (38, 38, 38)

    dark_window = FakeImage()

    assert screen_has_content(dark_window) is True


def test_black_window_is_not_visible_content():
    class BlackImage:
        size = (32, 32)

        def load(self):
            return self

        def __getitem__(self, position):
            return (0, 0, 0)

    assert screen_has_content(BlackImage()) is False


def test_wechat_sender_passes_text_to_reference_ui_adapter():
    calls = []

    def fake_quick_send(text, who, verify):
        calls.append((text, who, verify))
        return True

    sender = WeChatUISender(send_func=fake_quick_send)

    result = sender.send("alice", "回复内容")

    assert result is True
    assert calls == [("回复内容", "alice", True)]


def test_wechat_sender_resolves_display_name_before_search():
    calls = []

    def fake_quick_send(text, who, verify):
        calls.append((text, who, verify))
        return True

    sender = WeChatUISender(
        send_func=fake_quick_send,
        name_resolver=lambda user: "联系人名称",
    )

    sender.send("wxid_example", "回复内容")

    assert calls == [("回复内容", "联系人名称", True)]


def test_group_approval_uses_normal_send_and_private_approval_uses_send():
    sender = FakeSender()
    queue = ApprovalQueue(sender)
    group_event = MessageEvent(user="room@chatroom", message={"type": "文本", "content": "群问题"})
    private_event = MessageEvent(user="alice", message={"type": "文本", "content": "私聊问题"})

    group_token = queue.enqueue(group_event, "群回复")
    private_token = queue.enqueue(private_event, "私聊回复")

    queue.approve(group_token)
    queue.approve(private_token)

    assert sender.calls == [
        ("room@chatroom", "群回复"),
        ("alice", "私聊回复"),
    ]


def test_wechat_sender_can_call_quote_reply_adapter():
    calls = []

    def fake_quick_reply(text, who, verify):
        calls.append((text, who, verify))
        return True

    sender = WeChatUISender(reply_func=fake_quick_reply)

    assert sender.reply("room@chatroom", "引用内容") is True
    assert calls == [("引用内容", "room@chatroom", True)]


def test_quote_failure_falls_back_to_normal_send_when_not_executed():
    calls = []

    class FailureResponse(dict):
        def __bool__(self):
            return False

    def fake_quick_reply(text, who, verify):
        calls.append(("quote", text, who, verify))
        return FailureResponse(status="失败", message="未找到回复入口")

    def fake_send(text, who, verify):
        calls.append(("send", text, who, verify))
        return True

    sender = WeChatUISender(send_func=fake_send, reply_func=fake_quick_reply)

    assert sender.reply("room@chatroom", "普通发送兜底") is True
    assert calls == [
        ("quote", "普通发送兜底", "room@chatroom", True),
        ("send", "普通发送兜底", "room@chatroom", True),
    ]
