from app.services.group_summary import GroupSummaryService
from app.services.bot_runtime import BotRuntime
from app.messages.reader import MessageEvent


class FakeDB:
    def get_messages(self, user, limit):
        assert user == "123@chatroom"
        return [
            {"type": "系统消息", "content": "[系统消息]", "sender_id": 4},
            {"type": "文本", "content": "wxid_sender:\n周五发布", "sender_id": 1},
            {"type": "文本", "content": "小红：我负责测试", "sender_id": 2},
        ]


class FakeAI:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return "群聊重点：周五发布。\n待办：小红负责测试。"


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue(self, event, text):
        self.calls.append((event, text))
        return "summary-reply"


def test_group_summary_filters_system_messages_and_calls_ai():
    ai = FakeAI()
    service = GroupSummaryService(FakeDB(), ai, max_messages=50)

    result = service.summarize("123@chatroom")

    assert "群聊重点" in result
    assert "[系统消息]" not in ai.calls[0][-1]["content"]
    assert "周五发布" in ai.calls[0][-1]["content"]


def test_runtime_routes_group_summary_command_to_summary_service():
    class Summary:
        def summarize(self, user):
            assert user == "123@chatroom"
            return "群聊总结内容"

    class UnexpectedAI:
        def generate_reply(self, event):
            raise AssertionError("summary command should not call normal AI service")

    queue = FakeQueue()
    runtime = BotRuntime(
        UnexpectedAI(),
        queue,
        bot_names={"机器人"},
        group_summary_service=Summary(),
    )
    event = MessageEvent(
        user="123@chatroom",
        message={"type": "文本", "content": "@机器人 总结最近群聊"},
    )

    assert runtime.handle_event(event) == "summary-reply"
    assert queue.calls[0][1] == "群聊总结内容"


def test_group_summary_replaces_identity_with_anonymous_member_label():
    class ContactDB(FakeDB):
        def get_nickname(self, user):
            return {"wxid_sender": "小明"}.get(user, user)

    ai = FakeAI()
    service = GroupSummaryService(ContactDB(), ai)

    service.summarize("123@chatroom")

    prompt = ai.calls[0][-1]["content"]
    assert "wxid_sender" not in prompt
    assert "小明" not in prompt
    assert "成员" in prompt


def test_group_summary_includes_message_count_by_person():
    class ContactDB(FakeDB):
        def get_messages(self, user, limit):
            return [
                {"type": "文本", "content": "wxid_sender:\n第一条", "sender_id": 1},
                {"type": "文本", "content": "wxid_sender:\n第二条", "sender_id": 1},
                {"type": "文本", "content": "wxid_other:\n第三条", "sender_id": 3},
            ]

        def get_nickname(self, user):
            return {"wxid_sender": "小明", "wxid_other": "小红"}.get(user, user)

    ai = FakeAI()
    service = GroupSummaryService(ContactDB(), ai)

    service.summarize("123@chatroom")
    prompt = ai.calls[0][-1]["content"]

    assert "人员消息统计" in prompt
    assert "小明" not in prompt
    assert "小红" not in prompt
    assert "成员1：1 条" in prompt
    assert "成员2：2 条" in prompt
    assert "wxid_sender" not in prompt
    assert "wxid_other" not in prompt
