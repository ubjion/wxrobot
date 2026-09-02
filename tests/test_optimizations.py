import threading
import time

from app.messages.reader import MessageEvent
from app.services.knowledge_base import KnowledgeChunk
from app.services.reply_service import AiReplyService
from app.services.wechat_sender import WeChatUISender


def test_wechat_sender_reuses_gui_instance():
    created = []

    class FakeGUI:
        pass

    sender = WeChatUISender(gui_factory=lambda: created.append(FakeGUI()) or created[-1])

    first = sender._get_gui()
    second = sender._get_gui()

    assert first is second
    assert len(created) == 1


def test_knowledge_and_web_search_run_in_parallel():
    active = 0
    peak = 0
    lock = threading.Lock()
    both_started = threading.Event()
    ai_calls = []

    def enter_search():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 2:
                both_started.set()
        both_started.wait(timeout=1)
        time.sleep(0.02)
        with lock:
            active -= 1

    class Knowledge:
        def search(self, query, user_id, group_id=None, limit=5):
            enter_search()
            return [KnowledgeChunk(1, "本地资料", "local.md", "本地答案", "public")]

    class Web:
        def search(self, query):
            enter_search()
            return []

    class AI:
        def complete(self, messages):
            ai_calls.append(messages)
            return "回答"

    service = AiReplyService(AI(), knowledge_base=Knowledge(), search_client=Web())
    assert service.generate_reply(
        MessageEvent(user="alice", message={"type": "文本", "content": "最新问题"})
    ) == "回答"

    assert peak == 2
    assert "本地答案" in ai_calls[0][-1]["content"]
