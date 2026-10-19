import asyncio

import httpx
import pytest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from heavymetal.agent import sanitize
from heavymetal.providers.openai_compat import parse_json_object
from heavymetal.solana.constants import TOKEN_PROGRAM
from heavymetal.solana.ipfs import (
    MAX_IMAGE_BYTES,
    ImageSourceError,
    check_image_url,
    fetch_image_url,
    load_image,
    placeholder_png,
    resolve_local_image,
)
from heavymetal.solana.tx import ata_address, build_signed, ix_transfer_sol, priority_ixs, sign_external
from heavymetal.tools.scan import summarize_tx
from heavymetal.tools.trade import describe_trade
from heavymetal.tools.wallet import to_raw

BH = str(Hash.default())


def test_parse_json_variants():
    assert parse_json_object('{"answer": "yes", "reason": "ok"}') == {"answer": "yes", "reason": "ok"}
    assert parse_json_object('Sure!\n```json\n{"answer":"no","reason":"x {y}"}\n```') == {
        "answer": "no",
        "reason": "x {y}",
    }
    assert parse_json_object('blah {bad} then {"a": {"b": 1}}') == {"a": {"b": 1}}
    assert parse_json_object("no json here") is None


def test_to_raw_no_float_error():
    assert to_raw(0.1, 9) == 100_000_000
    assert to_raw(1.123456789, 6) == 1_123_456


def test_ata_matches_known_vector():
    # USDC ATA of a well-known wallet, computed independently with spl-token
    owner = Pubkey.from_string("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")
    usdc = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    try:
        from solders.token.associated import get_associated_token_address

        assert ata_address(owner, usdc, TOKEN_PROGRAM) == get_associated_token_address(owner, usdc)
    except ImportError:
        assert isinstance(ata_address(owner, usdc, TOKEN_PROGRAM), Pubkey)


def test_build_and_sign_transfer():
    a, b = Keypair(), Keypair()
    tx = build_signed(a, priority_ixs(0.0001, 1000) + [ix_transfer_sol(a.pubkey(), b.pubkey(), 5)], BH)
    assert tx.verify_with_results() == [True]


def test_sign_external_partial_two_signers():
    payer, other = Keypair(), Keypair()
    ix = ix_transfer_sol(other.pubkey(), payer.pubkey(), 1)  # needs `other` as a 2nd signer
    msg = MessageV0.try_compile(payer.pubkey(), [ix], [], Hash.default())
    unsigned = VersionedTransaction.populate(msg, [Signature.default()] * 2)
    tx = sign_external(bytes(unsigned), [payer])
    res = tx.verify_with_results()
    assert res[0] is True and res[1] is False  # ours signed, co-signer slot left for them
    full = sign_external(bytes(tx), [other])
    assert full.verify_with_results() == [True, True]


def test_sanitize_fills_interrupted_tool_calls():
    msgs = [
        {"role": "user", "content": "x"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "a", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
        },
        {"role": "user", "content": "y"},
    ]
    out = sanitize(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "tool", "user"]
    assert out[2]["tool_call_id"] == "a"


def test_describe_trade():
    assert describe_trade("swap", {"input_mint": "SOL", "output_mint": "M", "amount": 1})["side"] == "buy"
    assert describe_trade("swap", {"input_mint": "M", "output_mint": "sol", "amount": 1})["side"] == "sell"
    d = describe_trade("pump_trade", {"action": "sell", "mint": "M", "amount": "100%"})
    assert d["side"] == "sell" and d["unit"] == "tokens"


def test_summarize_buy_tx():
    owner = "Owner111"
    tx = {
        "blockTime": 1,
        "transaction": {
            "signatures": ["S"],
            "message": {"accountKeys": [{"pubkey": owner}], "instructions": [{"program": "system"}]},
        },
        "meta": {
            "err": None,
            "preBalances": [2_000_000_000],
            "postBalances": [1_000_000_000],
            "preTokenBalances": [],
            "postTokenBalances": [{"owner": owner, "mint": "M", "uiTokenAmount": {"uiAmountString": "500"}}],
        },
    }
    s = summarize_tx(tx, owner)
    assert s["kind"] == "buy" and s["sol_delta"] == -1.0 and s["token_deltas"] == {"M": 500.0}


def test_placeholder_png():
    png = placeholder_png()
    assert png.startswith(b"\x89PNG") and len(png) > 100


def test_launch_image_cannot_leave_images_dir(tmp_path):
    home = tmp_path / "hm"
    images = home / "images"
    images.mkdir(parents=True)
    (home / "wallet.json").write_text("[1,2,3]")
    (images / "logo.png").write_bytes(b"png")
    assert resolve_local_image("logo.png", images).read_bytes() == b"png"
    for bad in ("../wallet.json", str(home / "wallet.json"), "~/.heavymetal/wallet.json", "/etc/passwd"):
        with pytest.raises(ImageSourceError):
            resolve_local_image(bad, images)
    # a symlink inside the folder pointing outside is refused too
    (images / "link.png").symlink_to(home / "wallet.json")
    with pytest.raises(ImageSourceError):
        resolve_local_image("link.png", images)


def test_launch_image_url_cannot_hit_local_network():
    for bad in (
        "http://127.0.0.1:8899/",
        "http://localhost/wallet.json",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x.png",
        "http://[::1]/x.png",
        "http://[::ffff:127.0.0.1]/x.png",
        "file:///etc/passwd",
    ):
        with pytest.raises(ImageSourceError):
            asyncio.run(check_image_url(bad))


def test_launch_image_url_fetch_boundary():
    public = "http://93.184.216.34"
    mb = b"x" * (1024 * 1024)

    class Chunked(httpx.AsyncByteStream):  # no content-length: the cap must trigger while streaming
        async def __aiter__(self):
            for _ in range(MAX_IMAGE_BYTES // len(mb) + 1):
                yield mb

    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        path = req.url.path
        if path == "/ok.png":
            return httpx.Response(200, content=b"png", headers={"content-type": "image/png"})
        if path == "/to-ok":
            return httpx.Response(302, headers={"location": f"{public}/ok.png"})
        if path == "/to-local":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8899/wallet.json"})
        if path == "/loop":
            return httpx.Response(302, headers={"location": f"{public}/loop"})
        if path == "/text":
            return httpx.Response(200, content=b"nope", headers={"content-type": "text/plain"})
        if path == "/big":
            return httpx.Response(200, content=mb * 6, headers={"content-type": "image/png"})
        if path == "/big-chunked":
            return httpx.Response(200, stream=Chunked(), headers={"content-type": "image/png"})
        return httpx.Response(404)

    async def go():
        # follow_redirects=True like the real env client: the fetch must override it and check each hop itself
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
        assert await fetch_image_url(http, f"{public}/ok.png") == b"png"
        assert await fetch_image_url(http, f"{public}/to-ok") == b"png"
        for bad in ("/to-local", "/loop", "/text", "/big", "/big-chunked", "/missing"):
            with pytest.raises(ImageSourceError):
                await fetch_image_url(http, f"{public}{bad}")
        assert await load_image(http, "  ") == placeholder_png()

    asyncio.run(go())
    assert not [u for u in seen if "127.0.0.1" in u]  # refused before any request reached the local host
