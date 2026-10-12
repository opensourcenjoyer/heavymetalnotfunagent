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
    assert "claude-haiku-4-5" in AVAILABLE_MODELS
    assert "claude-sonnet-5-5" in AVAILABLE_MODELS
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


def test_anthropic_env_only_selects_claude(monkeypatch, tmp_path):
    from heavymetal import config as config_mod
    from heavymetal.env import make_agent_llm
    from heavymetal.providers.anthropic_provider import AnthropicProvider

    monkeypatch.setenv("HEAVYMETAL_HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cfg = config_mod.load()
    assert cfg.llm.agent_model == config_mod.ANTHROPIC_DEFAULT_MODEL
    assert isinstance(make_agent_llm(cfg, cfg.llm.agent_model), AnthropicProvider)

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")  # both keys: keep the configured default
    assert config_mod.load().llm.agent_model == "deepseek/deepseek-v4-flash"
