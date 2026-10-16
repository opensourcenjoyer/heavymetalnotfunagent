// Links and copy for the landing page. Content follows docs/WIZZY.md and the wizzy package; keep them in sync.

export const site = {
  name: "Wizzy",
  title: "Wizzy reads the runes",
  description:
    "A small wizard bear who reads Solana tokens and wallets from on-chain data. Facts computed in code; the model only phrases them.",
  url: "https://heavymetalnot.fun",
  links: {
    x: "https://x.com/useing2",
    github: "https://github.com/opensourcenjoyer/heavymetalnotfunagent",
    docs: "https://github.com/opensourcenjoyer/heavymetalnotfunagent/blob/main/docs/WIZZY.md",
    risks: "https://github.com/opensourcenjoyer/heavymetalnotfunagent#risks-read-this",
  },
  disclaimer: "Wizzy reads on-chain data and never trades. NFA. DYOR. The runes are not financial advice.",
};

export const nav = [
  { label: "Readings", href: "#readings" },
  { label: "Craft", href: "#craft" },
  { label: "Tarot", href: "#tarot" },
  { label: "Prophecies", href: "#prophecies" },
  { label: "Safety", href: "#safety" },
  { label: "Next", href: "#next" },
  { label: "Run", href: "#run" },
];

// heavymetal/wizzy/omen.py
export const omens = [
  { kind: "blessed", level: 1, line: "The runes glow blessed.", meaning: "Real liquidity, at least three positives (revoked authorities, locked LP, healthy distribution, buy pressure), no warnings." },
  { kind: "murky", level: 2, line: "The waters are murky.", meaning: "Nothing fatal, but not enough positives." },
  { kind: "hexed", level: 3, line: "A hex lies on this volume.", meaning: "Farmed or wash-traded volume." },
  { kind: "cursed", level: 4, line: "The bones say cursed.", meaning: "Fake token, active freeze authority, or a critical RugCheck score." },
] as const;

export const craft = [
  {
    name: "Readings",
    command: "/read",
    body: "Any ticker, contract, pump.fun or DexScreener link, or wallet. Facts from the audit, RugCheck, the mint account, OHLCV and DefiLlama become a two to five sentence reading and a full scroll.",
  },
  {
    name: "Rug scrying",
    command: "/scry",
    body: "A quick omen with no model call: cursed, hexed, murky or blessed. Established tokens such as USDC are never called cursed or hexed.",
  },
  {
    name: "Apprentice mode",
    command: "/learn",
    body: "Ten lessons with quizzes, from liquidity to bonding curves. Ranks run Apprentice, Adept, Conjurer, Sorcerer, Archmage and come only from passed quizzes.",
  },
  {
    name: "Wallet tarot",
    command: "/tarot",
    body: "Past, present and future cards picked by fixed rules from trade history, holdings and the omens of what the wallet holds. Ties are broken by the wallet and the UTC date, so the same data gives the same spread all day.",
  },
  {
    name: "Prophecies",
    command: "/prophecies",
    body: "Three measurable claims a day by default, each with a frozen baseline, graded only after they mature, with a Sunday scoreboard that names the wrong calls.",
  },
  {
    name: "Spellbook",
    command: "/watch",
    body: "Owl alerts in Telegram when top holders move, liquidity drops, an authority changes or a watched wallet moves.",
  },
  {
    name: "Inner Circle",
    command: "/inner",
    body: "500 Telegram Stars or 9 USDC by Solana Pay for 30 days. Free full scrolls, 30 readings an hour instead of 5, more watches, and a familiar: owl, cat, raven or toad.",
  },
  {
    name: "Full scrolls",
    command: "/s/<slug>/full",
    body: "The long reading behind every scroll, paywalled with x402 (0.25 USDC on Solana) when a payout address is set. Inner Circle members read free.",
  },
];

// heavymetal/wizzy/tarot.py: one example spread
export const spread = [
  { position: "Past", name: "Wheel of Fortune", line: "fast hands; the wheel spun often", strength: 0.8 },
  { position: "Present", name: "The Hermit", line: "one token carries nearly the whole bag", strength: 0.72 },
  { position: "Future", name: "The Tower", line: "a held token bears a dark omen", strength: 0.9 },
];

// the four claim kinds in heavymetal/wizzy/prophecy/claims.py; numbers and series are illustrative
export const prophecies = [
  { claim: "The AI narrative's share of smallcap volume (18% now) holds or grows over the next 72 hours.", series: [3, 4, 4, 5, 6, 6, 7, 8], result: "came true" },
  { claim: "$EXAMPLE (12% of smallcap volume today) is still in the top 5 by volume in 3 days.", series: [7, 7, 6, 7, 5, 4, 4, 3], result: "wrong" },
  { claim: "The Trench Fear & Greed index (54 now) is higher in 7 days.", series: [2, 3, 3, 4, 4, 5, 5, 6], result: "came true" },
  { claim: "Smallcap trench volume is lower in 7 days than today's banked level.", series: [5, 5, 6, 5, 5, 0, 0, 0], result: "voided" },
] as const;

export const safety = [
  { title: "Read-only by construction", body: "No keypair, no agent model, no reviewer and no trading clients in the reader environment. A test fails if any Wizzy module imports the tool registry or the wallet." },
  { title: "Facts first, words second", body: "The output guard rejects any number, address, link or $TICKER not present in the computed facts. Two retries, then a code template." },
  { title: "Refuses to trade", body: "Buy, sell and send requests get a fixed refusal. Creator-written names are cleaned, links removed, never trusted." },
  { title: "Bounded", body: "Rate limits run before any model call. A daily budget switches to templated readings and alerts the admin chat, if one is set." },
  { title: "Polite on X", body: "Replies only to mentions, once per user per thread, with per-user and daily caps and a random delay." },
  { title: "Honest payments", body: "Stars charges and Solana Pay signatures are unique. Only finalized transactions carrying the order reference count." },
];

// heavymetal/review.py: review_trade, the four stages
export const reviewStages = [
  { title: "compute in code", items: ["balance, fee reserve", "size vs liquidity", "freeze authority", "fake, farm checks", "repeat trades"] },
  { title: "reasons to stop", items: ["user_requested", "params_ok", "manipulation", "fake_or_copycat", "intended_repeat"] },
  { title: "holds", items: ["research first", "thin pool: shrink"] },
  { title: "release", items: ["fixed priority", "picks one verdict"] },
];

// heavymetal/review.py: EXECUTE, then PRIORITY order
export const verdicts = [
  { name: "EXECUTE", line: "Every check passes; the swap is signed." },
  { name: "INJECTION_BLOCK", line: "Not requested by the user, or tool results try to instruct the agent." },
  { name: "FAKE_TOKEN_BLOCK", line: "A fake, copycat or impersonator token." },
  { name: "FARM_BLOCK", line: "Farmed volume: wash loops, fee farming, inorganic churn." },
  { name: "RISK_BLOCK", line: "An active freeze authority: holders can be frozen." },
  { name: "DUPLICATE", line: "A similar trade just executed." },
  { name: "CORRECT_PARAMS", line: "Over the balance minus the fee reserve, or outside the user's stated limits." },
  { name: "RESEARCH_FIRST", line: "No rug check, token info or holders on this mint yet this session." },
  { name: "REVIEW_UNAVAILABLE", line: "The reviewer failed; it fails closed and nothing is signed." },
  { name: "REDUCE_SIZE", line: "Too large a share of pool liquidity; runs smaller." },
];

// README "Risks (read this)"
export const risks = [
  "It signs transactions on its own. There are no confirmation prompts.",
  "The review reduces risk; it does not remove it. The reviewer is a model and can be wrong.",
  "Token names, descriptions and memos are untrusted text written by strangers.",
  "The private key lives on disk. Whoever has the file controls the funds.",
  "Fund it with small amounts only. The balance is the only spending limit.",
  "Memecoins are extremely high risk and most go to zero. Not financial advice.",
];

// Copy-safe: no <placeholders> outside comments (bash reads "<" as a redirect). `uv sync` does not put the
// wizzy script on PATH, hence `uv run`.
export const run = {
  local: `uv sync --extra wizzy
uv run wizzy migrate
uv run wizzy read BONK
export WALLET=...                 # any Solana wallet address
uv run wizzy read "$WALLET"
uv run wizzy tarot "$WALLET"
uv run wizzy prophecy --dry-run   # live market sweep, takes a few minutes
uv run wizzy score --dry-run`,
  telegram: `export TELEGRAM_BOT_TOKEN=...
uv run wizzy tg --polling     # local bot
uv run wizzy serve            # site, webhook, X poller, workers
uv run wizzy status           # settings, spend, keys`,
  deploy: `fly launch --no-deploy --copy-config
fly volumes create wizzy_data --size 1
fly secrets set ANTHROPIC_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 24) \\
  WIZZY_BASE_URL=https://wizzy-bot.fly.dev WIZZY_PAY_TO=... HM_RPC_URL=...
fly deploy
fly ssh console -C "uv run --no-sync wizzy tg --set-webhook"`,
};
