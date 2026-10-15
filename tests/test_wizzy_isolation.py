"""Wizzy must never be able to touch the wallet or the trading tools."""

import json
import os
import pathlib
import re
import subprocess
import sys

WIZZY_DIR = pathlib.Path(__file__).resolve().parents[1] / "heavymetal" / "wizzy"
FORBIDDEN = [
    r"heavymetal\.tools",
    r"jup\.swap",
    r"send_and_confirm",
    r"build_signed",
    r"load_or_create",
    r"wallet_path",
]

PROBE = r"""
import json, sys, os, asyncio
from heavymetal.wizzy.ctx import open_ctx
import heavymetal.wizzy.main, heavymetal.wizzy.db
for name in {modules}:
    __import__(name)
ctx = open_ctx()
out = {{
  "tools": sorted(m for m in sys.modules if m.startswith("heavymetal.tools")),
  "kp_none": ctx.env.kp is None,
  "has_swap": hasattr(ctx.env.jup, "swap") or hasattr(ctx.env.jup, "order"),
  "cluster": ctx.env.cluster,
  "llm": ctx.env.agent_llm, "decider": ctx.env.decider, "pump": ctx.env.pump,
}}
try:
    ctx.env.address
    out["address"] = "exposed"
except RuntimeError:
    out["address"] = "raises"
asyncio.run(ctx.aclose())
print(json.dumps(out, default=str))
"""


def wizzy_modules() -> list[str]:
    mods = []
    for p in sorted(WIZZY_DIR.rglob("*.py")):
        rel = p.relative_to(WIZZY_DIR.parents[1]).with_suffix("")
        name = ".".join(rel.parts)
        if name.endswith(".__init__"):
            name = name[: -len(".__init__")]
        mods.append(name)
    return mods


def test_no_forbidden_references_in_wizzy_source():
    hits = []
    for p in WIZZY_DIR.rglob("*.py"):
        text = p.read_text()
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text):
                hits.append(f"{p.name}: {m.group(0)}")
    assert hits == []


def test_wizzy_imports_never_load_tools_or_wallet(tmp_path):
    env = {**os.environ, "HEAVYMETAL_HOME": str(tmp_path), "ANTHROPIC_API_KEY": ""}
    code = PROBE.format(modules=repr(wizzy_modules()))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["tools"] == []
    assert out["kp_none"] is True
    assert out["address"] == "raises"
    assert out["has_swap"] is False
    assert out["cluster"] == "mainnet"
    assert out["llm"] is None and out["decider"] is None and out["pump"] is None
    assert not (tmp_path / "wallet.json").exists()
    assert (tmp_path / "wizzy.db").exists()
