"""Facts: the only data the writer may use (PDF section 3), as pydantic models.

Everything here is computed in code from heavymetal's data clients. ``untrusted`` holds text written by token
creators (names, symbols); it is cleaned and clipped and the writer treats it as data, never instructions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OmenKind = Literal["cursed", "hexed", "murky", "blessed"]


class Source(BaseModel):
    name: str
    fetchedAt: float
    ok: bool = True


class Subject(BaseModel):
    kind: Literal["token", "wallet", "narrative"]
    mint: str | None = None
    symbol: str | None = None
    wallet: str | None = None


class Supply(BaseModel):
    total: float | None = None
    circulating: float | None = None


class Authorities(BaseModel):
    mint: str | None = None
    freeze: str | None = None


class Holders(BaseModel):
    top10Pct: float | None = None
    countApprox: int | None = None


class OhlcvSummary(BaseModel):
    change24hPct: float | None = None
    high24h: float | None = None
    low24h: float | None = None
    volume24hUsd: float | None = None
    candles: int = 0
    source: str | None = None


class Protocol(BaseModel):
    name: str
    slug: str
    category: str | None = None
    tvlUsd: float | None = None
    fees24hUsd: float | None = None


class Omen(BaseModel):
    kind: OmenKind
    reasons: list[str] = Field(default_factory=list)


class Farm(BaseModel):
    isFarm: bool = False
    kind: str | None = None


class TokenFacts(BaseModel):
    mint: str
    symbol: str | None = None
    name: str | None = None
    decimals: int | None = None
    priceUsd: float | None = None
    jupiterPriceUsd: float | None = None
    mcapUsd: float | None = None
    fdvUsd: float | None = None
    liquidityUsd: float | None = None
    volume24hUsd: float | None = None
    priceChange24hPct: float | None = None
    ageHours: float | None = None
    dex: str | None = None
    supply: Supply = Field(default_factory=Supply)
    authorities: Authorities = Field(default_factory=Authorities)
    holders: Holders = Field(default_factory=Holders)
    ohlcvSummary: OhlcvSummary = Field(default_factory=OhlcvSummary)
    lpLockedPct: float | None = None
    rugScore: float | None = None
    farm: Farm = Field(default_factory=Farm)
    verdictKey: str | None = None
    omen: Omen | None = None
    protocol: Protocol | None = None


class Holding(BaseModel):
    mint: str
    symbol: str | None = None
    amount: float | None = None
    usd: float | None = None
    sharePct: float | None = None


class WalletFacts(BaseModel):
    address: str
    solBalance: float | None = None
    solUsdPrice: float | None = None
    totalUsd: float | None = None
    tokenCount: int = 0
    topHoldings: list[Holding] = Field(default_factory=list)


class NarrativeFacts(BaseModel):
    theme: str
    relatedMints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Facts(BaseModel):
    asOf: float
    subject: Subject
    sources: list[Source] = Field(default_factory=list)
    token: TokenFacts | None = None
    wallet: WalletFacts | None = None
    narrative: NarrativeFacts | None = None
    extra: dict = Field(default_factory=dict)  # feature-specific computed facts (tarot cards, prophecy claims)
    strengths: list[str] = Field(default_factory=list)  # positive code findings
    unknowns: list[str] = Field(default_factory=list)
    riskFlags: list[str] = Field(default_factory=list)
    untrusted: dict[str, str] = Field(default_factory=dict)

    def for_writer(self) -> dict:
        """JSON-able dict for the writer prompt (drops empty fields to save tokens)."""
        d = self.model_dump(exclude_none=True, exclude_defaults=False)
        d.get("extra", {}).pop("chart", None)  # raw candles are for charts, not for prose
        return d
