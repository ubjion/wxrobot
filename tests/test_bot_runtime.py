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
