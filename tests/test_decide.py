import json

import httpx
from conftest import run

from heavymetal.config import Config
from heavymetal.decide import ChatDecider, DecisionsDecider, Question, make_decider
from heavymetal.providers.types import ProviderResponse

QS = [Question("a", "is a?", "yes a", "not a"), Question("b", "is b?", "yes b", "not b")]


def test_decisions_decider_batches_and_thresholds():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "model": "typesafe/jev-1.13-x",
                "answers": {"a": {"type": "noul", "noul": 0.93}, "b": {"type": "noul", "noul": 0.2}},
                "usage": {"input_tokens": 100, "output_tokens": 10, "cost": 2e-5},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    d = DecisionsDecider(http, "k", "typesafe/jev-1.13", "https://openrouter.ai/api/v1", zdr=True)
    res = run(d.decide(QS, {"x": 1}))
    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["body"]["provider"]["zdr"] is True
    assert set(seen["body"]["questions"]) == {"a", "b"}
    assert seen["body"]["questions"]["a"]["criteria"] == {"true": "yes a", "false": "not a"}
    assert res.answers["a"].value is True and res.answers["b"].value is False
    assert res.answers["a"].p == 0.93 and res.cost_usd == 2e-5 and not res.errors


def test_decisions_decider_error_marks_all_failed():
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad")))
    d = DecisionsDecider(http, "k", "typesafe/jev-1.13", "https://openrouter.ai/api/v1", zdr=True)
    res = run(d.decide(QS, {}))
    assert set(res.errors) == {"a", "b"} and not res.answers


class FakeProvider:
    model = "any/model"

    async def complete_json(self, system, user, keys):
        ans = "yes" if "is a?" in user else "no"
        return {"answer": ans, "reason": "r"}, ProviderResponse(cost_usd=1e-5, input_tokens=5, output_tokens=2)


def test_chat_decider_one_call_per_question():
    res = run(ChatDecider(FakeProvider()).decide(QS, {"tool_results": ["x"]}))
    assert res.answers["a"].value is True and res.answers["b"].value is False
    assert abs(res.cost_usd - 2e-5) < 1e-12


def test_make_decider_auto():
    cfg = Config()
    assert isinstance(make_decider(cfg, httpx.AsyncClient()), DecisionsDecider)
    cfg.llm.review_model = "deepseek/deepseek-v4-flash"
    assert isinstance(make_decider(cfg, httpx.AsyncClient()), ChatDecider)


def test_make_decider_anthropic_routing():
    import httpx

    from heavymetal.config import Config
    from heavymetal.decide import ChatDecider, DecisionsDecider, make_decider
    from heavymetal.providers.anthropic_provider import AnthropicProvider

    http = httpx.AsyncClient()
    # Anthropic-only: default Jev reviewer is unreachable -> Claude fallback, not REVIEW_UNAVAILABLE
    cfg = Config()
    cfg.llm.anthropic_key = "sk-ant-test"
    d = make_decider(cfg, http)
    assert isinstance(d, ChatDecider) and isinstance(d.provider, AnthropicProvider)
    assert d.model == "claude-haiku-4-5"

    # explicit claude-* review model goes to Anthropic even when an OpenRouter key exists
    cfg.llm.api_key = "sk-or-test"
    cfg.llm.review_model = "claude-sonnet-5-5"
    d = make_decider(cfg, http)
    assert isinstance(d.provider, AnthropicProvider) and d.model == "claude-sonnet-5-5"

    # OpenRouter key present: default Jev decisions reviewer is unchanged
    cfg.llm.review_model = "typesafe/jev-1.13"
    assert isinstance(make_decider(cfg, http), DecisionsDecider)
