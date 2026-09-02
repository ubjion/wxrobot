"""Firecrawl 通用网页搜索适配器。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import time
from typing import Any


logger = logging.getLogger("wx-bot")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    description: str


class WebSearchError(RuntimeError):
    """联网搜索失败。"""


class FirecrawlSearchClient:
    def __init__(self, api_key: str | None = None, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return
        key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
        if not key.strip():
            self._client = None
            return
        try:
            from firecrawl import Firecrawl
        except ImportError as exc:
            raise WebSearchError("未安装 firecrawl-py 依赖") from exc
        self._client = Firecrawl(api_key=key)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("搜索关键词不能为空")
        if limit <= 0:
            raise ValueError("limit must be positive")
        if self._client is None:
            raise WebSearchError("未配置 FIRECRAWL_API_KEY")
        started = time.perf_counter()
        try:
            response = self._client.search(query, sources=["web"], limit=limit)
            items = getattr(response, "web", None)
            if items is None and isinstance(response, dict):
                items = response.get("web")
        except Exception as exc:
            logger.warning("联网搜索失败，耗时 %.2f 秒", time.perf_counter() - started)
            raise WebSearchError(f"联网搜索失败：{type(exc).__name__}") from exc
        results = []
        for item in items or []:
            title = self._value(item, "title") or "无标题"
            url = self._value(item, "url")
            description = self._value(item, "description") or self._value(item, "snippet")
            if url:
                results.append(SearchResult(title, url, description or ""))
        logger.info("联网搜索耗时 %.2f 秒，结果 %d 条", time.perf_counter() - started, len(results))
        return results

    @staticmethod
    def _value(item: Any, field: str) -> str:
        value = item.get(field) if isinstance(item, dict) else getattr(item, field, "")
        return value.strip() if isinstance(value, str) else ""
