import pytest

from app.services.prompt_loader import PromptLoadError, load_system_prompt


def test_loads_prompt_from_explicit_file(tmp_path):
    prompt_file = tmp_path / "assistant.md"
    prompt_file.write_text("你是一个测试助手。", encoding="utf-8")

    assert load_system_prompt(prompt_file) == "你是一个测试助手。"


def test_environment_path_overrides_default(monkeypatch, tmp_path):
    prompt_file = tmp_path / "custom.md"
    prompt_file.write_text("自定义提示词", encoding="utf-8")
    monkeypatch.setenv("WX_BOT_PROMPT_FILE", str(prompt_file))

    assert load_system_prompt() == "自定义提示词"


def test_missing_explicit_prompt_file_raises_clear_error(tmp_path):
    with pytest.raises(PromptLoadError, match="提示词文件不存在"):
        load_system_prompt(tmp_path / "missing.md")


def test_empty_prompt_file_raises_clear_error(tmp_path):
    prompt_file = tmp_path / "empty.md"
    prompt_file.write_text("\n", encoding="utf-8")

    with pytest.raises(PromptLoadError, match="提示词文件为空"):
        load_system_prompt(prompt_file)
