from app.messages.reader import MessageEvent
from app.services.bot_runtime import BotRuntime


class FakeAI:
    def __init__(self, reply="AI 回复"):
        self.reply = reply

    def generate_reply(self, event):
        return self.reply


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue(self, event, text):
        self.calls.append((event, text))
        return "reply-1"


def test_runtime_enqueues_ai_reply_without_sending_it():
    queue = FakeQueue()
    runtime = BotRuntime(FakeAI(), queue)
    event = MessageEvent(user="alice", message={"type": "文本", "content": "你好"})

    token = runtime.handle_event(event)

    assert token == "reply-1"
    assert queue.calls == [(event, "AI 回复")]


def test_runtime_ignores_events_without_reply():
    class NoReplyAI:
        def generate_reply(self, event):
            return None

    queue = FakeQueue()
    runtime = BotRuntime(NoReplyAI(), queue)

    assert runtime.handle_event(
        MessageEvent(user="alice", message={"type": "图片", "content": ""})
    ) is None
    assert queue.calls == []


def test_runtime_auto_mode_approves_reply_immediately():
    class AutoQueue(FakeQueue):
        def __init__(self):
            super().__init__()
            self.approved = []

        def approve(self, token):
            self.approved.append(token)
            return True

    queue = AutoQueue()
    runtime = BotRuntime(FakeAI(), queue, auto_send=True)
    event = MessageEvent(user="alice", message={"type": "文本", "content": "你好"})

    assert runtime.handle_event(event) == "reply-1"
    assert queue.approved == ["reply-1"]


def test_runtime_ignores_messages_sent_by_self():
    queue = FakeQueue()
    runtime = BotRuntime(FakeAI(), queue, auto_send=True)
    event = MessageEvent(
        user="alice",
        message={"type": "文本", "content": "自己的消息", "sender_id": 2},
    )

    assert runtime.handle_event(event) is None
    assert queue.calls == []


def test_runtime_ignores_group_message_without_bot_mention():
    queue = FakeQueue()
    runtime = BotRuntime(FakeAI(), queue, bot_names={"机器人"})
    event = MessageEvent(
        user="123@chatroom",
        message={"type": "文本", "content": "大家今天几点开会"},
    )

    assert runtime.handle_event(event) is None
    assert queue.calls == []


def test_runtime_replies_when_group_message_mentions_bot_name():
    queue = FakeQueue()
    runtime = BotRuntime(FakeAI(), queue, bot_names={"机器人"})
    event = MessageEvent(
        user="123@chatroom",
        message={"type": "文本", "content": "@机器人 请总结一下"},
    )

    assert runtime.handle_event(event) == "reply-1"
    assert len(queue.calls) == 1


def test_runtime_uses_fallback_reply_when_ai_fails():
    class FailingAI:
        def generate_reply(self, event):
            raise RuntimeError("AI unavailable")

    queue = FakeQueue()
    runtime = BotRuntime(
        FailingAI(),
        queue,
        fallback_reply="我收到啦，AI 暂时不可用，请稍后再试。",
    )
    event = MessageEvent(user="alice", message={"type": "文本", "content": "你好"})

    assert runtime.handle_event(event) == "reply-1"
    assert queue.calls[0][1] == "我收到啦，AI 暂时不可用，请稍后再试。"
