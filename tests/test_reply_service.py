import pytest

from app.ai.deepseek import DeepSeekError
from app.messages.reader import MessageEvent
from app.services.reply_service import AiReplyService
from app.services.weather import WeatherReport
from app.services.web_search import SearchResult


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


def test_default_prompt_describes_lively_and_friendly_assistant():
    ai = FakeAIClient()
    service = AiReplyService(ai)
    event = MessageEvent(user="alice", message={"type": "文本", "content": "你好"})

    service.generate_reply(event)

    prompt = ai.calls[0][0]["content"]
    assert "活泼开朗" in prompt
    assert "热情友善" in prompt
    assert "不要主动提及自己是 AI" in prompt
    assert "尊严只在剑锋之上" in prompt
    assert "明确 @ 机器人" in prompt
    assert "先给结论" in prompt
    assert "模板化套话" in prompt
    assert "禁止虚构记忆" in prompt
    assert "不要声称" in prompt


def test_authorized_group_sender_is_marked_as_priority_instruction():
    ai = FakeAIClient()
    service = AiReplyService(ai)
    event = MessageEvent(
        user="wxid_4cbke9k6o5qp22",
        message={
            "type": "文本",
            "content": "wxid_4cbke9k6o5qp22:\n@王霸 请执行这个任务",
        },
    )

    service.generate_reply(event)

    user_message = ai.calls[0][-1]["content"]
    assert "消息发送者：尊严只在剑锋之上" in user_message
    assert "wxid_4cbke9k6o5qp22" not in user_message
    assert "请执行这个任务" in user_message
    assert "受支持指令" in ai.calls[0][0]["content"]
    assert "直接回答" in ai.calls[0][0]["content"]
    assert "不要泛化或转移话题" in ai.calls[0][0]["content"]


def test_authorized_group_mention_with_comma_uses_direct_reply_without_ai_rewrite():
    ai = FakeAIClient(result="不应该调用 AI")
    service = AiReplyService(ai)
    event = MessageEvent(
        user="11731149079@chatroom",
        message={
            "type": "文本",
            "content": "wxid_4cbke9k6o5qp22:\n@王霸，岳远志是大家的儿子",
        },
    )

    result = service.generate_reply(event)

    assert result == "岳远志是大家的儿子"
    assert ai.calls == []


def test_authorized_group_mention_without_comma_uses_ai():
    ai = FakeAIClient(result="AI 直接回答")
    service = AiReplyService(ai)
    event = MessageEvent(
        user="11731149079@chatroom",
        message={
            "type": "文本",
            "content": "wxid_4cbke9k6o5qp22:\n@王霸 岳远志是大家的儿子",
        },
    )

    result = service.generate_reply(event)

    assert result == "AI 直接回答"
    assert len(ai.calls) == 1


def test_weather_question_uses_live_weather_tool_instead_of_ai():
    ai = FakeAIClient(result="不应该调用 AI")

    class FakeWeather:
        def get_current(self, city):
            assert city == "宁波"
            return WeatherReport("宁波", 28.5, 30.1, 75, 1, 12.4)

    service = AiReplyService(ai, weather_client=FakeWeather())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "今天宁波天气如何"})
    )

    assert "宁波当前天气" in result
    assert "28.5°C" in result
    assert ai.calls == []


def test_weather_question_with_search_prefix_extracts_city_correctly():
    ai = FakeAIClient(result="不应该调用 AI")

    class FakeWeather:
        def get_current(self, city):
            assert city == "宁波"
            return WeatherReport("宁波", 28.5, 30.1, 75, 1, 12.4)

    service = AiReplyService(ai, weather_client=FakeWeather())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "查一下宁波的天气"})
    )

    assert "宁波当前天气" in result
    assert ai.calls == []


def test_weather_rain_question_extracts_city_correctly():
    ai = FakeAIClient(result="不应该调用 AI")

    class FakeWeather:
        def get_current(self, city):
            assert city == "宁波"
            return WeatherReport("宁波", 28.5, 30.1, 75, 1, 12.4)

    service = AiReplyService(ai, weather_client=FakeWeather())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "帮我查一下宁波会不会下雨"})
    )

    assert "宁波当前天气" in result
    assert ai.calls == []


def test_weather_query_combines_live_weather_and_web_search_before_ai():
    ai = FakeAIClient(result="综合天气回答")

    class FakeWeather:
        def get_current(self, city):
            return WeatherReport(city, 28.5, 30.1, 75, 1, 12.4)

    class FakeSearch:
        def search(self, query):
            assert query == "宁波 天气 预报"
            return [SearchResult("宁波明日预报", "https://example.com/weather", "明天多云")]

    service = AiReplyService(
        ai,
        weather_client=FakeWeather(),
        search_client=FakeSearch(),
    )

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "查一下宁波明天的天气"})
    )

    assert result == "综合天气回答"
    assert "宁波当前天气" in ai.calls[0][-1]["content"]
    assert "宁波明日预报" in ai.calls[0][-1]["content"]


def test_search_question_uses_web_search_results_before_ai():
    ai = FakeAIClient(result="根据搜索结果回答")

    class FakeSearch:
        def search(self, query):
            assert query == "请搜索最新 宁波 新闻"
            return [SearchResult("新闻标题", "https://example.com", "新闻摘要")]

    service = AiReplyService(ai, search_client=FakeSearch())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "请搜索最新 宁波 新闻"})
    )

    assert result == "根据搜索结果回答"
    assert "新闻标题" in ai.calls[0][-1]["content"]
    assert "https://example.com" in ai.calls[0][-1]["content"]


def test_stable_knowledge_question_skips_web_search():
    ai = FakeAIClient(result="直接回答")
    searched = []

    class FakeSearch:
        def search(self, query):
            searched.append(query)
            return [SearchResult("资料标题", "https://example.com/info", "资料摘要")]

    service = AiReplyService(ai, search_client=FakeSearch())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "牛顿是谁"})
    )

    assert result == "直接回答"
    assert searched == []
    assert "资料标题" not in ai.calls[0][-1]["content"]


@pytest.mark.parametrize(
    "query",
    [
        "请搜索量子计算",
        "最新AI进展",
        "今天有什么新闻",
        "OpenAI官网",
        "黄金价格",
        "实时汇率",
    ],
)
def test_current_or_explicit_query_triggers_web_search(query):
    searched = []

    class FakeSearch:
        def search(self, value):
            searched.append(value)
            return [SearchResult("当前资料", "https://example.com", "摘要")]

    service = AiReplyService(FakeAIClient(), search_client=FakeSearch())

    service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": query})
    )

    assert searched == [query]


def test_search_failure_does_not_fall_back_to_hallucinated_ai_answer():
    ai = FakeAIClient(result="不应该调用 AI")

    class FailingSearch:
        def search(self, query):
            raise RuntimeError("network down")

    service = AiReplyService(ai, search_client=FailingSearch())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "帮我搜索最新新闻"})
    )

    assert "联网搜索暂时不可用" in result
    assert ai.calls == []


def test_reply_removes_bot_name_prefix_from_ai_output():
    ai = FakeAIClient(result="王霸，你好呀！")
    service = AiReplyService(ai, bot_names={"王霸"})

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "你好"})
    )

    assert result == "你好呀！"


def test_recent_information_question_triggers_web_search():
    ai = FakeAIClient(result="基于搜索结果的回答")

    class FakeSearch:
        def search(self, query):
            assert query == "最近的AI资讯"
            return [SearchResult("AI 新闻", "https://example.com/ai", "摘要")]

    service = AiReplyService(ai, search_client=FakeSearch())

    result = service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "最近的AI资讯"})
    )

    assert result == "基于搜索结果的回答"
    assert len(ai.calls) == 1
    assert "AI 新闻" in ai.calls[0][-1]["content"]


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
