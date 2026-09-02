"""DeepSeek OpenAI-compatible Chat Completions client."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import time
from typing import Any, Mapping, Sequence


logger = logging.getLogger("wx-bot")


class DeepSeekError(RuntimeError):
    """可安全展示给用户的 DeepSeek 调用错误。"""


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout: float = 30.0
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        return cls(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", cls.base_url),
            model=os.getenv("DEEPSEEK_MODEL", cls.model),
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT", str(cls.timeout))),
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", str(cls.temperature))),
        )


class DeepSeekClient:
    """调用 DeepSeek Chat Completions，不负责微信发送。"""

    def __init__(self, config: DeepSeekConfig, sdk_client: Any | None = None) -> None:
        if not config.api_key.strip():
            raise ValueError("DeepSeek API Key 不能为空")
        if config.timeout <= 0:
            raise ValueError("timeout must be positive")
        if not 0 <= config.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        self.config = config
        self._client = sdk_client or self._create_sdk_client(config)

    @staticmethod
    def _create_sdk_client(config: DeepSeekConfig) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise DeepSeekError("未安装 openai 依赖，请先安装项目依赖") from exc
        return OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=0,
        )

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        if not messages:
            raise ValueError("messages 不能为空")
        payload = [dict(message) for message in messages]
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=payload,
                stream=False,
                temperature=self.config.temperature,
            )
        except Exception as exc:
            logger.warning("DeepSeek 请求失败，耗时 %.2f 秒", time.perf_counter() - started)
            raise DeepSeekError(f"DeepSeek 请求失败：{type(exc).__name__}") from exc
        logger.info("DeepSeek 请求耗时 %.2f 秒", time.perf_counter() - started)

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek 返回格式无效") from exc
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek 返回空回复")
        return content.strip()
