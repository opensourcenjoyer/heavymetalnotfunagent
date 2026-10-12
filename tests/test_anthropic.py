import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from heavymetal.providers.anthropic_provider import (
    AnthropicProvider,
    convert_messages,
    convert_tool_schemas,
    estimate_cost,
)


def test_convert_tool_schemas():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "token_audit",
                "description": "audit token",
                "parameters": {
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"],
                },
            },
        }
    ]
    res = convert_tool_schemas(tools)
    assert len(res) == 1
    assert res[0]["name"] == "token_audit"
    assert res[0]["description"] == "audit token"
    assert "input_schema" in res[0]
    assert res[0]["input_schema"]["properties"]["target"]["type"] == "string"


def test_convert_messages_structure():
    messages = [
        {"role": "system", "content": "You are heavymetalagent."},
        {"role": "user", "content": "Check token DezX..."},
        {
            "role": "assistant",
            "content": "Analyzing...",
            "tool_calls": [
                {
                    "id": "tool_123",
                    "type": "function",
                    "function": {"name": "token_audit", "arguments": '{"target": "DezX..."}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tool_123", "content": '{"status": "success", "verdict": "BULLISH"}'},
    ]

    system, ant_msgs = convert_messages(messages)
    assert system == "You are heavymetalagent."
    assert len(ant_msgs) == 3

    # User message
    assert ant_msgs[0]["role"] == "user"
    assert ant_msgs[0]["content"] == "Check token DezX..."

    # Assistant message with tool_use block
    assert ant_msgs[1]["role"] == "assistant"
    blocks = ant_msgs[1]["content"]
    assert len(blocks) == 2
    assert blocks[0]["type"] == "text" and blocks[0]["text"] == "Analyzing..."
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["id"] == "tool_123"
    assert blocks[1]["name"] == "token_audit"
    assert blocks[1]["input"] == {"target": "DezX..."}

    # Tool result inside user message
    assert ant_msgs[2]["role"] == "user"
    res_blocks = ant_msgs[2]["content"]
    assert len(res_blocks) == 1
    assert res_blocks[0]["type"] == "tool_result"
    assert res_blocks[0]["tool_use_id"] == "tool_123"
    assert "BULLISH" in res_blocks[0]["content"]


def test_estimate_cost():
    # 1,000 in, 1,000 out on Claude 3.5 Sonnet ($3 / $15)
    cost = estimate_cost("claude-3-5-sonnet-latest", 1_000, 1_000)
    assert cost == 0.018

    # 10,000 in, 1,000 out on Claude 3.5 Haiku ($0.80 / $4.0)
    cost_haiku = estimate_cost("claude-3-5-haiku-20241022", 10_000, 1_000)
    assert cost_haiku == 0.012


@pytest.mark.anyio
async def test_anthropic_provider_call():
    provider = AnthropicProvider(api_key="sk-ant-test", model="claude-3-5-sonnet-latest")

    # Mock response
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Audit complete."

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "call_abc"
    tool_block.name = "token_audit"
    tool_block.input = {"target": "So111..."}

    mock_resp = MagicMock()
    mock_resp.content = [text_block, tool_block]
    mock_resp.usage.input_tokens = 500
    mock_resp.usage.output_tokens = 150
    mock_resp.model = "claude-3-5-sonnet-20241022"

    provider.client.messages.create = AsyncMock(return_value=mock_resp)

    messages = [{"role": "user", "content": "Audit So111..."}]
    res = await provider.complete(messages)

    assert res.content == "Audit complete."
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "token_audit"
    assert json.loads(res.tool_calls[0].arguments) == {"target": "So111..."}
    assert res.input_tokens == 500
    assert res.output_tokens == 150
    assert res.cost_usd > 0
