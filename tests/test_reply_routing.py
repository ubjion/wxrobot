from app.services.reply_routing import (
    extract_weather_city,
    format_web_results,
    is_weather_query,
    should_search_web,
)
from app.services.web_search import SearchResult


def test_weather_routing_detects_query_and_extracts_city():
    assert is_weather_query("帮我查一下宁波会不会下雨") is True
    assert extract_weather_city("帮我查一下宁波会不会下雨") == "宁波"
    assert is_weather_query("牛顿是谁") is False


def test_search_routing_distinguishes_stable_and_current_questions():
    assert should_search_web("牛顿是谁") is False
    assert should_search_web("最新AI新闻") is True
    assert should_search_web("请搜索OpenAI官网") is True


def test_web_formatter_delimits_and_limits_untrusted_fields():
    formatted = format_web_results([
        SearchResult("T" * 300, "https://example.com/" + "u" * 600, "D" * 2000)
    ])

    assert formatted.startswith("BEGIN_UNTRUSTED_WEB_RESULTS\n")
    assert formatted.endswith("\nEND_UNTRUSTED_WEB_RESULTS")
    lines = formatted.splitlines()
    assert len(next(line for line in lines if line.startswith("标题："))[3:]) == 200
    assert len(next(line for line in lines if line.startswith("链接："))[3:]) == 500
    assert len(next(line for line in lines if line.startswith("摘要："))[3:]) == 1000
