"""Anthropic native API provider: supports Claude 3.5 Sonnet, Claude 3.7, Claude 3.5 Haiku.

Converts internal OpenAI-style conversation history & tool schemas to Anthropic's Messages format:
- System prompt -> top-level `system` parameter
- Tool schemas -> Anthropic `input_schema`
- Assistant tool calls -> `tool_use` content blocks
- Tool results -> `tool_result` content blocks inside user messages
- Streaming deltas -> `on_delta(kind, text)` callback
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from heavymetal.providers.openai_compat import parse_json_object
from heavymetal.providers.types import DeltaCallback, ProviderResponse, ToolCall

# Pricing per 1M tokens ($in, $out)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (3.0, 15.0),
    "claude-opus-5-5": (15.0, 75.0),
    "claude-fable-5-1": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3-7-sonnet": (3.0, 15.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-3-opus": (15.0, 75.0),
}


class AnthropicProviderError(RuntimeError):
    pass


def convert_tool_schemas(tools: Sequence[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function", t)
        out.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def convert_messages(messages: Sequence[dict]) -> tuple[str, list[dict]]:
    """Separates system prompt and formats alternating user/assistant/tool messages for Anthropic."""
    system_parts = []
    anthropic_msgs: list[dict] = []
    pending_tool_results: list[dict] = []

    for m in messages:
        role = m.get("role")
        content = m.get("content")

        if role == "system":
            if content:
                system_parts.append(str(content))
            continue

        if role == "tool":
            # Tool result block
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": str(content or ""),
                }
            )
            continue

        # If we had accumulated tool results, flush them as a user message
        if pending_tool_results:
            anthropic_msgs.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results.clear()

        if role == "assistant":
            blocks = []
            if content:
                blocks.append({"type": "text", "text": str(content)})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw_args = fn.get("arguments", "{}")
                try:
                    args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:  # noqa: BLE001
                    args_dict = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args_dict,
                    }
                )
            anthropic_msgs.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})

        elif role == "user":
            anthropic_msgs.append({"role": "user", "content": str(content or "")})

    # Flush any remaining tool results
    if pending_tool_results:
        anthropic_msgs.append({"role": "user", "content": list(pending_tool_results)})

    return "\n\n".join(system_parts), anthropic_msgs


def estimate_cost(model_name: str, in_tokens: int, out_tokens: int) -> float:
    for prefix, (pin, pout) in MODEL_PRICING.items():
        if prefix in model_name.lower():
            return round((in_tokens * pin + out_tokens * pout) / 1_000_000, 6)
    return round((in_tokens * 3.0 + out_tokens * 15.0) / 1_000_000, 6)


class AnthropicProvider:
    is_openrouter: bool = False

    def __init__(self, api_key: str, model: str = "claude-sonnet-5-5", base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.is_openrouter = False
        kw: dict[str, Any] = {"api_key": api_key or "none"}
        if base_url:
            kw["base_url"] = base_url
        self.client = AsyncAnthropic(**kw)

    async def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict] | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> ProviderResponse:
        system_prompt, ant_messages = convert_messages(messages)
        ant_tools = convert_tool_schemas(tools)

        # Ensure valid starting message
        if not ant_messages:
            ant_messages = [{"role": "user", "content": "Hello"}]
        elif ant_messages[0]["role"] != "user":
            ant_messages.insert(0, {"role": "user", "content": "Begin conversation."})

        kw: dict[str, Any] = {
            "model": self.model,
            "messages": ant_messages,
            "max_tokens": 4096,
        }
        if system_prompt:
            kw["system"] = system_prompt
        if ant_tools:
            kw["tools"] = ant_tools

        try:
            if on_delta is not None:
                return await self._stream(kw, on_delta)
            return await self._call(kw)
        except anthropic.APIError as e:
            raise AnthropicProviderError(f"Anthropic error ({self.model}): {e}") from e

    async def _call(self, kw: dict) -> ProviderResponse:
        resp = await self.client.messages.create(**kw)
        content_text = ""
        tool_calls: list[ToolCall] = []

        for block in resp.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        tin = resp.usage.input_tokens
        tout = resp.usage.output_tokens
        cost = estimate_cost(self.model, tin, tout)

        return ProviderResponse(
            content=content_text,
            tool_calls=tool_calls,
            input_tokens=tin,
            output_tokens=tout,
            cost_usd=cost,
            model=resp.model or self.model,
        )

    async def _stream(self, kw: dict, on_delta: DeltaCallback) -> ProviderResponse:
        content_text = ""
        tool_calls: list[ToolCall] = []

        tin = 0
        tout = 0

        async with self.client.messages.stream(**kw) as stream:
            async for event in stream:
                if event.type == "text":
                    content_text += event.text
                    on_delta("content", event.text)
                elif event.type == "thinking" and hasattr(event, "thinking"):
                    on_delta("reasoning", event.thinking)

            final_msg = await stream.get_final_message()
            tin = final_msg.usage.input_tokens
            tout = final_msg.usage.output_tokens

            for block in final_msg.content:
                if block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=json.dumps(block.input),
                        )
                    )

        cost = estimate_cost(self.model, tin, tout)
        return ProviderResponse(
            content=content_text,
            tool_calls=tool_calls,
            input_tokens=tin,
            output_tokens=tout,
            cost_usd=cost,
            model=self.model,
        )

    async def complete_json(self, system: str, user: str, keys: Sequence[str]) -> tuple[dict, ProviderResponse]:
        messages = [
            {
                "role": "system",
                "content": system + "\n\nReply with ONE valid JSON object only. No prose, no code fences.",
            },
            {"role": "user", "content": user},
        ]
        total = ProviderResponse(model=self.model, cost_usd=0.0)
        for _ in range(2):
            resp = await self.complete(messages)
            total.input_tokens += resp.input_tokens
            total.output_tokens += resp.output_tokens
            total.cost_usd = (total.cost_usd or 0) + (resp.cost_usd or 0)
            data = parse_json_object(resp.content)
            if data is not None and all(k in data for k in keys):
                return data, total
            messages += [
                {"role": "assistant", "content": resp.content},
                {
                    "role": "user",
                    "content": f"Invalid format. Output only a JSON object containing keys: {', '.join(keys)}.",
                },
            ]
        raise AnthropicProviderError(f"{self.model}: no valid JSON with keys {list(keys)}")
