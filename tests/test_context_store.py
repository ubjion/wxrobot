from app.messages.reader import MessageEvent
from app.services.context_store import JsonContextStore
from app.services.reply_service import AiReplyService


class FakeAI:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return "AI 回复"


def test_context_store_keeps_conversations_isolated_by_user_id(tmp_path):
    store = JsonContextStore(tmp_path / "contexts.json", max_messages=4)

    store.append_exchange("alice", "你好", "你好呀")
    store.append_exchange("bob", "在吗", "在的")

    assert store.get_messages("alice") == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好呀"},
    ]
    assert store.get_messages("bob") == [
        {"role": "user", "content": "在吗"},
        {"role": "assistant", "content": "在的"},
    ]


def test_context_store_keeps_only_latest_messages(tmp_path):
    store = JsonContextStore(tmp_path / "contexts.json", max_messages=2)

    store.append_exchange("alice", "第一句", "第一答")
    store.append_exchange("alice", "第二句", "第二答")

    assert store.get_messages("alice") == [
        {"role": "user", "content": "第二句"},
        {"role": "assistant", "content": "第二答"},
    ]


def test_reply_service_sends_and_persists_user_specific_context(tmp_path):
    ai = FakeAI()
    store = JsonContextStore(tmp_path / "contexts.json")
    store.append_exchange("alice", "之前的问题", "之前的回答")
    service = AiReplyService(ai, context_store=store)

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "继续说"})
    )

    assert result == "AI 回复"
    assert ai.calls[0][1:3] == [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]
    assert store.get_messages("alice")[-2:] == [
        {"role": "user", "content": "继续说"},
        {"role": "assistant", "content": "AI 回复"},
    ]
