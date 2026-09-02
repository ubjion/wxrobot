from types import SimpleNamespace
import logging

from app.services.web_search import FirecrawlSearchClient, SearchResult


def test_firecrawl_search_maps_web_results(caplog):
    class FakeFirecrawl:
        def search(self, query, sources, limit):
            assert query == "最新 宁波 新闻"
            assert sources == ["web"]
            assert limit == 5
            return SimpleNamespace(web=[
                SimpleNamespace(url="https://example.com", title="标题", description="摘要")
            ])

    client = FirecrawlSearchClient(client=FakeFirecrawl())
    caplog.set_level(logging.INFO, logger="wx-bot")

    assert client.search("最新 宁波 新闻") == [
        SearchResult("标题", "https://example.com", "摘要")
    ]
    assert "联网搜索耗时" in caplog.text


def test_firecrawl_search_returns_empty_results_when_provider_has_no_web_bucket():
    class FakeFirecrawl:
        def search(self, query, sources, limit):
            return SimpleNamespace(web=None)

    assert FirecrawlSearchClient(client=FakeFirecrawl()).search("查询") == []
