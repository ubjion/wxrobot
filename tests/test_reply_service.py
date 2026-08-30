from app.ai.deepseek import DeepSeekError
from app.messages.reader import MessageEvent
from app.services.reply_service import AiReplyService


class FakeAIClient:
    def __init__(self, result="收到"):
        self.result = result
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return self.result


def test_generates_reply_from_text_event_without_sending_session_identifier():
    ai = FakeAIClient(result="好的，我来处理")
    service = AiReplyService(ai, system_prompt="你是测试助手")
    event = MessageEvent(
        user="private-user",
        message={"type": "文本", "content": "请帮我总结"},
    )

    result = service.generate_reply(event)

    assert result == "好的，我来处理"
    assert ai.calls == [[
        {"role": "system", "content": "你是测试助手"},
        {"role": "user", "content": "请帮我总结"},
    ]]
    assert "private-user" not in str(ai.calls)


def test_ignores_empty_message_without_calling_ai():
    ai = FakeAIClient()
    service = AiReplyService(ai)
    event = MessageEvent(user="alice", message={"type": "文本", "content": "  "})

    assert service.generate_reply(event) is None
    assert ai.calls == []


def test_propagates_ai_error_for_listener_level_handling():
    class FailingAI:
        def complete(self, messages):
            raise DeepSeekError("请求失败")

    service = AiReplyService(FailingAI())
    event = MessageEvent(user="alice", message={"type": "文本", "content": "你好"})

    try:
        service.generate_reply(event)
    except DeepSeekError as exc:
        assert str(exc) == "请求失败"
    else:
        raise AssertionError("DeepSeekError should be propagated")
