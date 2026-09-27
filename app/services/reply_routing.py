"""回复服务使用的纯意图判断、文本提取和外部资料格式化。"""

from __future__ import annotations

import re
from typing import Any, Iterable


def is_weather_query(content: str) -> bool:
    return any(word in content for word in ("天气", "气温", "温度", "下雨", "降雨"))


def should_search_web(content: str) -> bool:
    normalized = content.strip().lower()
    if not normalized:
        return False
    markers = (
        "搜索", "搜一下", "搜一搜", "查找", "查一下", "官网", "网址", "链接",
        "最新", "最近", "今天", "当前", "现在", "实时", "新闻", "资讯",
        "价格", "汇率", "行情",
    )
    return any(marker in normalized for marker in markers)


def extract_weather_city(content: str) -> str | None:
    content = re.sub(
        r"^(?:请|帮我|麻烦)?\s*(?:查一下|查下|查询|查查|看看|了解一下)\s*",
        "",
        content,
    )
    match = re.search(
        r"([\u4e00-\u9fff]{2,8}?)(?:今天|明天|后天|现在|当前)(?:的)?天气",
        content,
    )
    if match:
        return match.group(1)
    match = re.search(
        r"(?:今天|明天|后天|现在|当前)?([\u4e00-\u9fff]{2,8}?)(?:市)?(?:的)?天气",
        content,
    )
    if match:
        return match.group(1)
    match = re.search(
        r"([\u4e00-\u9fff]{2,8}?)(?:市)?(?:今天|明天|后天|现在|当前)?"
        r"(?:会不会|是否|会)?(?:下雨|降雨)",
        content,
    )
    if match:
        return match.group(1)
    match = re.search(r"天气(?:在|是)?([\u4e00-\u9fff]{2,8})", content)
    return match.group(1) if match else None


def format_web_results(results: Iterable[Any], max_chars: int = 6000) -> str:
    begin = "BEGIN_UNTRUSTED_WEB_RESULTS"
    end = "END_UNTRUSTED_WEB_RESULTS"
    blocks: list[str] = []
    used = len(begin) + len(end) + 2

    def clean(value: Any, limit: int) -> str:
        text = value.strip() if isinstance(value, str) else ""
        text = text.replace(begin, "[FILTERED_MARKER]")
        text = text.replace(end, "[FILTERED_MARKER]")
        return text[:limit]

    for index, item in enumerate(results, 1):
        block = (
            f"{index}.\n"
            f"标题：{clean(item.title, 200)}\n"
            f"链接：{clean(item.url, 500)}\n"
            f"摘要：{clean(item.description, 1000)}"
        )
        extra = len(block) + (1 if blocks else 0)
        if used + extra > max_chars:
            break
        blocks.append(block)
        used += extra
    return f"{begin}\n" + "\n".join(blocks) + f"\n{end}"
