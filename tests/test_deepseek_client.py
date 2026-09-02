from types import SimpleNamespace
import logging

import pytest

from app.ai.deepseek import DeepSeekClient, DeepSeekConfig, DeepSeekError


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeSDKClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def test_complete_returns_assistant_content_and_sends_configured_request(caplog):
    completions = FakeCompletions(
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="你好"))]
        )
    )
    client = DeepSeekClient(
        DeepSeekConfig(api_key="test-key", model="deepseek-v4-flash"),
        sdk_client=FakeSDKClient(completions),
    )
    caplog.set_level(logging.INFO, logger="wx-bot")

    result = client.complete([{"role": "user", "content": "你好"}])

    assert result == "你好"
    assert "DeepSeek 请求耗时" in caplog.text
    assert completions.calls == [
        {
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "你好"}],
            "stream": False,
            "temperature": 0.7,
        }
    ]


def test_complete_wraps_provider_errors_without_exposing_api_key():
    completions = FakeCompletions(error=RuntimeError("provider failed"))
    client = DeepSeekClient(
        DeepSeekConfig(api_key="super-secret", model="deepseek-v4-flash"),
        sdk_client=FakeSDKClient(completions),
    )

    with pytest.raises(DeepSeekError, match="请求失败") as exc_info:
        client.complete([{"role": "user", "content": "你好"}])

    assert "super-secret" not in str(exc_info.value)


def test_complete_rejects_empty_provider_response():
    completions = FakeCompletions(
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="  "))])
    )
    client = DeepSeekClient(
        DeepSeekConfig(api_key="test-key"),
        sdk_client=FakeSDKClient(completions),
    )

    with pytest.raises(DeepSeekError, match="空回复"):
        client.complete([{"role": "user", "content": "你好"}])


def test_config_loads_key_and_optional_values_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "custom-model")

    config = DeepSeekConfig.from_env()

    assert config.api_key == "env-key"
    assert config.base_url == "https://example.test"
    assert config.model == "custom-model"
