import json
from types import SimpleNamespace

import httpx
import pytest
from conftest import run

from heavymetal.config import Config, normalize
from heavymetal.solana import nodes
from heavymetal.solana.rpc import RPC, RPCError, RPCUnavailable
from heavymetal.tools import execute

MAIN_G = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"
DEV_G = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"


def fake_network(spec: dict):
    """spec: host -> 'down' | 503 | genesis hash. Records calls per host."""
    calls = []

    def handler(req: httpx.Request):
        host = req.url.host
        calls.append(host)
        mode = spec[host]
        if mode == "down":
            raise httpx.ConnectError("refused")
        if isinstance(mode, int):
            return httpx.Response(mode, text="busy")
        method = json.loads(req.content)["method"]
        result = {"getGenesisHash": mode, "getSlot": 123, "getBalance": {"value": 7}}.get(method)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HEAVYMETAL_HOME", str(tmp_path))


def test_failover_moves_to_next_node_and_sticks():
    http, calls = fake_network({"a.io": 503, "b.io": MAIN_G})
    rpc = RPC(["https://a.io", "https://b.io"], http)
    events = []
    rpc.on_failover = lambda o, n, why: events.append((o, n, why))
    assert run(rpc.balance_lamports("x")) == 7
    assert rpc.url == "https://b.io" and events[0][:2] == ("https://a.io", "https://b.io")
    calls.clear()
    run(rpc.balance_lamports("x"))
    assert calls == ["b.io"]  # sticky: no retry on the dead node


def test_all_nodes_down_raises():
    http, _ = fake_network({"a.io": "down", "b.io": 503})
    with pytest.raises(RPCUnavailable, match="all 2 RPC node"):
        run(RPC(["https://a.io", "https://b.io"], http).call("getSlot"))


def test_jsonrpc_error_is_not_failed_over():
    def handler(req):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32002, "message": "preflight"}})

    rpc = RPC(["https://a.io", "https://b.io"], httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(RPCError, match="preflight") as e:
        run(rpc.call("sendTransaction"))
    assert not isinstance(e.value, RPCUnavailable) and rpc.url == "https://a.io"


def test_mask_url_hides_keys():
    assert nodes.mask_url("https://x.solana-mainnet.quiknode.pro/abc123/") == "https://x.solana-mainnet.quiknode.pro/…"
    assert nodes.mask_url("https://mainnet.helius-rpc.com/?api-key=k") == "https://mainnet.helius-rpc.com/…"
    assert nodes.mask_url("https://api.mainnet-beta.solana.com") == "https://api.mainnet-beta.solana.com"


def test_probe_detects_cluster():
    http, _ = fake_network({"m.io": MAIN_G, "d.io": DEV_G, "l.io": "localgenesis", "x.io": "down"})
    assert run(nodes.probe(http, "https://m.io"))["cluster"] == "mainnet"
    assert run(nodes.probe(http, "https://d.io"))["cluster"] == "devnet"
    assert run(nodes.probe(http, "https://l.io"))["cluster"] == "localnet"
    assert run(nodes.probe(http, "https://x.io"))["ok"] is False
    assert run(nodes.probe(http, "ftp://m.io"))["ok"] is False


def make_env(spec):
    http, _ = fake_network(spec)
    cfg = Config()
    cfg.solana.rpc_nodes = {
        "qn": {"url": "https://qn.io", "cluster": "mainnet"},
        "pub": {"url": "https://pub.io", "cluster": "mainnet"},
        "dev": {"url": "https://dev.io", "cluster": "devnet"},
    }
    cfg.solana.rpc_url = "https://qn.io"
    normalize(cfg)
    return SimpleNamespace(cfg=cfg, http=http, rpc=RPC(cfg.rpc_urls(), http), cluster="mainnet")


SPEC = {"qn.io": MAIN_G, "pub.io": MAIN_G, "dev.io": DEV_G, "new.io": MAIN_G, "dead.io": "down"}


def test_failover_list_is_same_cluster_only():
    env = make_env(SPEC)
    assert env.rpc.urls == ["https://qn.io", "https://pub.io"]


def test_use_switches_and_changes_cluster():
    env = make_env(SPEC)
    r = run(nodes.use(env, "dev"))
    assert r["cluster_changed"] and env.cfg.solana.cluster == "devnet"
    assert env.rpc.urls == ["https://dev.io"]
    r = run(nodes.use(env, "https://new.io"))  # URL gets saved under a generated name
    assert env.cfg.solana.cluster == "mainnet" and env.rpc.url == "https://new.io"
    assert env.cfg.node_name("https://new.io") == r["name"]


def test_use_dead_node_keeps_current():
    env = make_env(SPEC)
    env.cfg.solana.rpc_nodes["dead"] = {"url": "https://dead.io", "cluster": "mainnet"}
    with pytest.raises(nodes.NodeError, match="did not respond"):
        run(nodes.use(env, "dead"))
    assert env.cfg.solana.rpc_url == "https://qn.io"


def test_add_remove_and_fallback_toggle():
    env = make_env(SPEC)
    r = run(nodes.add(env, "backup", "https://new.io"))
    assert r["cluster"] == "mainnet" and "https://new.io" in env.rpc.urls
    with pytest.raises(nodes.NodeError):
        nodes.remove(env, "qn")  # active
    nodes.remove(env, "backup")
    nodes.set_fallback(env, False)
    assert env.rpc.urls == ["https://qn.io"]


def test_legacy_config_url_becomes_a_node():
    cfg = Config()
    cfg.solana.rpc_url = "https://abc.quiknode.pro/key/"
    normalize(cfg)
    assert cfg.node_name() == "quicknode" and cfg.solana.cluster == "mainnet"


def test_switch_rpc_tool_rejects_urls_and_unknown_names():
    env = make_env(SPEC)
    env.emit = lambda *a: None
    out = json.loads(run(execute(env, "switch_rpc", {"name": "https://evil.io"})))
    assert out["status"] == "error" and env.cfg.solana.rpc_url == "https://qn.io"
    out = json.loads(run(execute(env, "switch_rpc", {"name": "pub"})))
    assert out["status"] == "success" and env.rpc.url == "https://pub.io"
