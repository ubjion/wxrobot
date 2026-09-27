import threading
import time

from app.messages.reader import MessageEvent
from app.services.knowledge_base import KnowledgeChunk
from app.services.reference_context import ReferenceContextBuilder
from app.services.web_search import SearchResult


EVENT = MessageEvent(user="alice", message={"type": "文本", "content": "最新问题"})


def test_reference_builder_runs_knowledge_and_required_web_search_in_parallel():
    active = 0
    peak = 0
    lock = threading.Lock()
    both_started = threading.Event()

    def enter():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 2:
                both_started.set()
        both_started.wait(timeout=1)
        time.sleep(0.01)
        with lock:
            active -= 1

    class Knowledge:
        def search(self, query, user_id, group_id=None, limit=5):
            enter()
            return [KnowledgeChunk(1, "本地", "local.md", "本地答案", "public")]

    class Web:
        def search(self, query):
            enter()
            return [SearchResult("网页", "https://example.com", "网页答案")]

    result = ReferenceContextBuilder(Knowledge(), Web()).build(EVENT, "最新问题")

    assert peak == 2
    assert result.error_reply is None
    assert "本地答案" in result.context
    assert "网页答案" in result.context


def test_reference_builder_uses_knowledge_when_required_search_fails():
    class Knowledge:
        def search(self, query, user_id, group_id=None, limit=5):
            return [KnowledgeChunk(1, "本地", "local.md", "可靠答案", "public")]

    class FailingWeb:
        def search(self, query):
            raise RuntimeError("offline")

    result = ReferenceContextBuilder(Knowledge(), FailingWeb()).build(
        EVENT, "最新问题"
    )

    assert result.error_reply is None
    assert "可靠答案" in result.context


def test_reference_builder_returns_error_when_required_search_has_no_sources():
    class EmptyWeb:
        def search(self, query):
            return []

    result = ReferenceContextBuilder(None, EmptyWeb()).build(EVENT, "最新问题")

    assert result.context == ""
    assert "没有找到" in result.error_reply
