from collections.abc import Callable
from dataclasses import dataclass, field

DeltaCallback = Callable[[str, str], None]  # (kind, text) kind: reasoning|content


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string from the model


@dataclass
class ProviderResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None  # OpenRouter-reported cost when available
    reasoning: str | None = None
    model: str = ""
