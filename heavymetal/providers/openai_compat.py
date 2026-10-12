"""Model-agnostic provider for any OpenAI-compatible endpoint (OpenRouter, Ollama, vLLM, ...).

OpenRouter extras (only sent when base_url is openrouter.ai):
  provider.zdr=true            route only to Zero Data Retention endpoints
  provider.data_collection     "deny" (never route to providers that train on prompts)
  usage.include=true           get the real per-call cost back
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from typing import Any

import openai
from openai import AsyncOpenAI

from heavymetal.providers.types import DeltaCallback, ProviderResponse, ToolCall

RETRY_DELAYS = [2, 5, 10, 20]
RETRYABLE = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)


class ProviderError(RuntimeError):
    pass


class OpenAICompatProvider:
    def __init__(self, api_key: str, model: str, base_url: str, zdr: bool = True):
        self.model = model
        self.base_url = base_url
        self.zdr = zdr
        self.is_openrouter = "openrouter.ai" in base_url
        self.client = AsyncOpenAI(api_key=api_key or "none", base_url=base_url)

    # ------------------------------------------------------------------ request
    def _kwargs(self, messages, tools, extra: dict | None = None) -> dict:
        kw: dict[str, Any] = {"model": self.model, "messages": list(messages)}
        if tools:
            kw["tools"] = list(tools)
            kw["tool_choice"] = "auto"
        body: dict[str, Any] = {}
        if self.is_openrouter:
            body["provider"] = {"data_collection": "deny"}
            if self.zdr:
                body["provider"]["zdr"] = True
            body["usage"] = {"include": True}
        if extra:
            body.update(extra)
        if body:
            kw["extra_body"] = body
        return kw

    async def _create(self, **kw):
        last = None
        for delay in RETRY_DELAYS + [None]:
            try:
                return await self.client.chat.completions.create(**kw)
            except RETRYABLE as e:
                last = e
                if delay is None:
                    break
                await asyncio.sleep(delay)
            except openai.APIStatusError as e:
                msg = str(e)
                if self.zdr and ("data policy" in msg.lower() or e.status_code == 404):
                    raise ProviderError(
                        f"No Zero-Data-Retention endpoint served '{self.model}' for this request. "
                        f"Pick a ZDR model (/zdr lists them) or set llm.zdr=false. ({msg[:200]})"
                    ) from e
                raise ProviderError(f"{self.model}: {msg[:400]}") from e
        raise ProviderError(f"{self.model}: gave up after retries: {last}")

    # ------------------------------------------------------------------ public
    async def complete(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict] | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> ProviderResponse:
        kw = self._kwargs(messages, tools)
        if on_delta is not None:
            try:
                return await self._stream(kw, on_delta)
            except ProviderError:
                raise
            except Exception:  # noqa: BLE001 - some endpoints reject streaming; degrade
                pass
        resp = await self._create(**kw)
        msg = resp.choices[0].message if resp.choices else None
        return ProviderResponse(
            content=(msg.content or "") if msg else "",
            tool_calls=[
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
                for tc in (msg.tool_calls or [])
            ]
            if msg
            else [],
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            cost_usd=_cost(resp.usage),
            reasoning=(getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)) if msg else None,
            model=getattr(resp, "model", self.model) or self.model,
        )

    async def _stream(self, kw: dict, on_delta: DeltaCallback) -> ProviderResponse:
        stream = await self._create(**kw, stream=True, stream_options={"include_usage": True})
        content, reasoning = [], []
        slots: dict[int, dict] = {}
        out = ProviderResponse(model=self.model)
        async for chunk in stream:
            if chunk.usage:
                out.input_tokens = chunk.usage.prompt_tokens or 0
                out.output_tokens = chunk.usage.completion_tokens or 0
                out.cost_usd = _cost(chunk.usage)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            r = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
            if r:
                reasoning.append(r)
                on_delta("reasoning", r)
            if delta.content:
                content.append(delta.content)
                on_delta("content", delta.content)
            for tc in delta.tool_calls or []:
                s = slots.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                if tc.id:
                    s["id"] = tc.id
                if tc.function:
                    s["name"] += tc.function.name or ""
                    s["args"] += tc.function.arguments or ""
        out.content = "".join(content)
        out.reasoning = "".join(reasoning) or None
        out.tool_calls = [
            ToolCall(id=s["id"] or f"call_{i}", name=s["name"], arguments=s["args"] or "{}")
            for i, s in sorted(slots.items())
        ]
        return out

    async def complete_json(self, system: str, user: str, keys: Sequence[str]) -> tuple[dict, ProviderResponse]:
        """Ask for a JSON object by prompt (works on models without response_format/tools).
        Validates required keys; one corrective retry."""
        messages = [
            {"role": "system", "content": system + "\n\nReply with ONE JSON object only. No prose, no code fences."},
            {"role": "user", "content": user},
        ]
        total = ProviderResponse(model=self.model, cost_usd=0.0)
        for _attempt in range(2):
            resp = await self.complete(messages)
            total.input_tokens += resp.input_tokens
            total.output_tokens += resp.output_tokens
            total.cost_usd = (total.cost_usd or 0) + (resp.cost_usd or 0)
            data = parse_json_object(resp.content)
            if data is not None and all(k in data for k in keys):
                return data, total
            messages += [
                {"role": "assistant", "content": resp.content},
                {"role": "user", "content": f"Invalid. Return only a JSON object with keys: {', '.join(keys)}."},
            ]
        raise ProviderError(f"{self.model}: no valid JSON with keys {list(keys)}")


def _cost(usage) -> float | None:
    if usage is None:
        return None
    c = getattr(usage, "cost", None)
    if c is None and getattr(usage, "model_extra", None):
        c = usage.model_extra.get("cost")
    try:
        return float(c) if c is not None else None
    except (TypeError, ValueError):
        return None


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json_object(text: str) -> dict | None:
    """Extract the first JSON object from model text (handles fences and leading prose)."""
    if not text:
        return None
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
        start = text.find("{", start + 1)
    return None
