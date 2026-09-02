from app.messages.reader import MessageEvent
from app.services.reply_service import AiReplyService
from app.services.knowledge_base import KnowledgeChunk


class FakeAI:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return "知识库回答"


def test_reply_includes_user_scoped_knowledge_before_ai():
    ai = FakeAI()

    class Knowledge:
        def search(self, query, user_id, group_id=None, limit=5):
            assert query == "退款规则是什么"
            assert user_id == "alice"
            return [KnowledgeChunk(1, "售后规则", "after_sale.md", "支持七天退款", "public")]

    service = AiReplyService(ai, knowledge_base=Knowledge())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "退款规则是什么"})
    )

    assert result == "知识库回答"
    assert "支持七天退款" in ai.calls[0][-1]["content"]
    assert "after_sale.md" in ai.calls[0][-1]["content"]
