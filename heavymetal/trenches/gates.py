"""Which pools count as smallcap volume. Each gate that drops a pool is counted with its dollars."""

from __future__ import annotations

from heavymetal.signals.farm import classify_farm, metrics_from
from heavymetal.solana.fake_check import normalize_ticker

MAJOR_MINTS = {
    "So11111111111111111111111111111111111111112",  # wSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB",  # USD1
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo",  # PYUSD
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # JitoSOL
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",  # bSOL
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",  # jupSOL
    "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",  # INF
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",  # cbBTC
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # WETH
}
STABLE_SYMBOLS = {
    "USDC",
    "USDT",
    "USD1",
    "PYUSD",
    "USDS",
    "USDE",
    "FDUSD",
    "USDG",
    "EURC",
    "USDH",
    "UXD",
    "USDY",
    "AUSD",
}
LST_SYMBOLS = {
    "SOL",
    "WSOL",
    "JITOSOL",
    "MSOL",
    "BSOL",
    "JUPSOL",
    "INF",
    "HSOL",
    "DSOL",
    "BNSOL",
    "JSOL",
    "STSOL",
    "VSOL",
    "BBSOL",
    "PSOL",
}
BIG_SYMBOLS = {"BTC", "WBTC", "CBBTC", "ETH", "WETH", "ZBTC", "TBTC", "XBTC"}
# Tokenized stocks / ETFs (xStocks style "NVDAx"). Only counted as equity when it trades above $1, so a
# meme squatting the ticker at a fraction of a cent stays in the trenches.
EQUITY_TICKERS = {
    "AAPL",
    "NVDA",
    "TSLA",
    "SPY",
    "QQQ",
    "MSTR",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "MSFT",
    "COIN",
    "CRCL",
    "HOOD",
    "NFLX",
    "AMD",
    "PLTR",
    "GME",
    "AVGO",
    "ORCL",
    "IBM",
    "INTC",
    "JPM",
    "V",
    "MA",
    "KO",
    "PEP",
    "MCD",
    "WMT",
    "DIS",
    "BABA",
    "GLD",
    "TQQQ",
    "VTI",
    "IWM",
    "SPCX",
    "CRWD",
    "UNH",
    "LLY",
    "XOM",
    "BAC",
    "CSCO",
    "ABT",
    "TMO",
    "PG",
    "JNJ",
    "HD",
    "CVX",
    "MRK",
    "PFE",
    "AZN",
    "NVO",
    "ACN",
    "DHR",
    "ABBV",
    "PM",
    "LIN",
    "MDT",
    "HON",
    "GS",
    "BRK",
    "BRKB",
    "OPEN",
    "AMBR",
    "DFDV",
    "SLV",
    "TBLL",
    "GLXY",
}


def _sym(s: str | None) -> str:
    return normalize_ticker(s or "").upper()


def is_major(mint: str | None, symbol: str | None, price: float | None) -> bool:
    if mint in MAJOR_MINTS:
        return True
    s = _sym(symbol)
    if s in STABLE_SYMBOLS and price and 0.9 < price < 1.25:
        return True
    if s in LST_SYMBOLS and price and price > 20:
        return True
    return bool(s in BIG_SYMBOLS and price and price > 500)


def is_equity(symbol: str | None, price: float | None) -> bool:
    s = normalize_ticker(symbol or "")
    if not price or price <= 1:
        return False
    core = s[:-1] if s.endswith(("x", "X")) and len(s) > 1 else s
    return core.upper() in EQUITY_TICKERS and (s.endswith("x") or s.endswith("X") or s.upper().endswith("ON"))


def gate_pool(p: dict, cfg) -> tuple[str | None, list[str]]:
    """Return (drop_reason or None, reasons). p: normalised GeckoTerminal pool row."""
    base_major = is_major(p.get("mint"), p.get("symbol"), p.get("price_usd"))
    quote_major = is_major(p.get("quote_mint"), p.get("quote_symbol"), None) or p.get("quote_mint") in MAJOR_MINTS
    if base_major and (quote_major or p.get("quote_symbol") is None):
        return "major", ["both sides are majors or stables: not speculation"]
    if base_major and not quote_major:
        # reversed pool (the meme is the quote): judge it on the quote side, which we can't price; keep it
        pass
    fdv = p.get("fdv") or p.get("market_cap")
    if fdv and fdv > cfg.signals.smallcap_fdv_cap:
        return "megacap", [f"FDV ${fdv:,.0f} is above the ${cfg.signals.smallcap_fdv_cap:,.0f} smallcap cap"]
    if is_equity(p.get("symbol"), p.get("price_usd")):
        return "equity", ["tokenized stock or ETF at a share price"]
    farm = classify_farm(metrics_from(gt=p), cfg)
    if farm.is_farm:
        return farm.kind, farm.reasons
    return None, []


def ticker_key(p: dict) -> str:
    """Same-ticker pools are one ticker: fee tiers and copycat mints alike."""
    return _sym(p.get("symbol")) or (p.get("mint") or "?")[:6]
