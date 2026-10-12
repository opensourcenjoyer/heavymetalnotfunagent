from types import SimpleNamespace

import pytest

from heavymetal.config import Config
from heavymetal.providers.anthropic_provider import AnthropicProvider
from heavymetal.providers.openai_compat import OpenAICompatProvider
from heavymetal.settings import AVAILABLE_MODELS, _mask, handle_settings_command


def test_models_list_contains_latest():
    assert "claude-sonnet-5-5" in AVAILABLE_MODELS
    assert "claude-opus-5-5" in AVAILABLE_MODELS
    assert "claude-fable-5-1" in AVAILABLE_MODELS
    assert "claude-haiku-5-5" in AVAILABLE_MODELS
    assert "claude-3-5-sonnet-latest" in AVAILABLE_MODELS
    assert "deepseek/deepseek-v4-flash" in AVAILABLE_MODELS


def test_mask_key():
    assert _mask("") == "[red]not set[/red]"
    assert _mask("1234") == "set"
    masked = _mask("sk-ant-api03-abcdef123456789")
    assert masked.startswith("sk-ant") and masked.endswith("6789")


@pytest.mark.anyio
async def test_handle_settings_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("HEAVYMETAL_HOME", str(tmp_path))
    cfg = Config()
    env = SimpleNamespace(cfg=cfg, http=None, agent_llm=None, decider=None)

    # 1. Update Anthropic key
    await handle_settings_command(env, ["anthropic", "sk-ant-testkey12345678"])
    assert env.cfg.llm.anthropic_key == "sk-ant-testkey12345678"

    # 2. Update model to Claude 5.5
    await handle_settings_command(env, ["model", "claude-sonnet-5-5"])
    assert env.cfg.llm.agent_model == "claude-sonnet-5-5"
    assert isinstance(env.agent_llm, AnthropicProvider)
    assert env.agent_llm.model == "claude-sonnet-5-5"

    # 3. Update model to DeepSeek
    await handle_settings_command(env, ["model", "deepseek/deepseek-v4-flash"])
    assert env.cfg.llm.agent_model == "deepseek/deepseek-v4-flash"
    assert isinstance(env.agent_llm, OpenAICompatProvider)

    # 4. Update provider
    await handle_settings_command(env, ["provider", "anthropic"])
    assert env.cfg.llm.provider == "anthropic"

    # 5. Show settings
    await handle_settings_command(env, ["show"])
