"""The agent wiki: bundled markdown pages (heavymetal/wiki/**) + the user's own (~/.heavymetal/wiki/**).

Pages start with a small front matter block:
    ---
    title: Wash loops
    tags: farm, wash, volume
    summary: one line
    ---
Search is SQLite FTS5 (bm25) over an in-memory index, rebuilt when a page is added.
User pages with the same slug override bundled ones.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
import time
from importlib import resources
from pathlib import Path

from heavymetal import paths

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9/_-]{0,80}$")


def user_dir() -> Path:
    d = paths.home() / "wiki"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse(text: str) -> tuple[dict, str]:
    meta: dict = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].strip().splitlines():
                k, _, v = line.partition(":")
                if k.strip():
                    meta[k.strip().lower()] = v.strip()
            body = text[end + 4 :].lstrip("\n")
    if "title" not in meta:
        m = re.search(r"^#\s+(.+)$", body, re.M)
        meta["title"] = m.group(1).strip() if m else ""
    return meta, body


class Wiki:
    def __init__(self, bundled: Path | None = None, user: Path | None = None):
        self.bundled = bundled
        self.user = user
        self.pages: dict[str, dict] = {}
        self.conn: sqlite3.Connection | None = None
        self.load()

    def _roots(self) -> list[tuple[str, Path]]:
        roots = []
        b = self.bundled or Path(str(resources.files("heavymetal") / "wiki"))
        if b.exists():
            roots.append(("bundled", b))
        u = self.user or user_dir()
        if u.exists():
            roots.append(("user", u))
        return roots

    def load(self) -> None:
        self.pages = {}
        for origin, root in self._roots():
            for f in sorted(root.rglob("*.md")):
                slug = f.relative_to(root).with_suffix("").as_posix()
                meta, body = parse(f.read_text(encoding="utf-8"))
                self.pages[slug] = {
                    "slug": slug,
                    "title": meta.get("title") or slug,
                    "tags": meta.get("tags", ""),
                    "summary": meta.get("summary", ""),
                    "verify": meta.get("verify", ""),
                    "body": body,
                    "origin": origin,
                    "path": str(f),
                    "meta": meta,
                }
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE VIRTUAL TABLE w USING fts5(slug, title, tags, summary, body, tokenize='porter unicode61')"
        )
        self.conn.executemany(
            "INSERT INTO w VALUES (?,?,?,?,?)",
            [(p["slug"], p["title"], p["tags"], p["summary"], p["body"]) for p in self.pages.values()],
        )

    def search(self, query: str, limit: int = 6) -> list[dict]:
        terms = [t for t in re.findall(r"[\w$.-]+", query.lower()) if len(t) > 1]
        if not terms or not self.conn:
            return []
        q = " OR ".join(f'"{t}"*' if len(t) > 3 else f'"{t}"' for t in terms)
        try:
            rows = self.conn.execute(
                "SELECT slug, snippet(w, 4, '«', '»', ' … ', 18), bm25(w, 2.0, 6.0, 4.0, 3.0, 1.0) s "
                "FROM w WHERE w MATCH ? ORDER BY s LIMIT ?",
                (q, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        return [
            {
                "slug": s,
                "title": self.pages[s]["title"],
                "summary": self.pages[s]["summary"],
                "snippet": snip,
                "origin": self.pages[s]["origin"],
            }
            for s, snip, _ in rows
            if s in self.pages
        ]

    def read(self, slug: str) -> dict | None:
        slug = slug.strip().strip("/").removesuffix(".md")
        p = self.pages.get(slug)
        if p is None:  # forgiving: match on the last path part or the title
            cands = [
                x for x in self.pages.values() if x["slug"].endswith("/" + slug) or x["title"].lower() == slug.lower()
            ]
            p = cands[0] if cands else None
        return p

    def index(self) -> list[dict]:
        return [
            {"slug": p["slug"], "title": p["title"], "summary": p["summary"], "origin": p["origin"]}
            for p in sorted(self.pages.values(), key=lambda x: x["slug"])
        ]

    def note(self, slug: str, title: str, body: str, tags: str = "", summary: str = "") -> dict:
        slug = slug.strip().strip("/").lower().removesuffix(".md")
        if not SLUG_RE.match(slug) or ".." in slug:
            raise ValueError("slug must be lowercase letters, digits, '-', '_' and '/' (e.g. notes/my-setup)")
        if not slug.startswith(("notes/", "cases/", "watch/")):
            slug = "notes/" + slug
        f = (self.user or user_dir()) / f"{slug}.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        clean = lambda s: s.replace("\n", " ").strip()  # noqa: E731
        f.write_text(
            f"---\ntitle: {clean(title)}\ntags: {clean(tags)}\nsummary: {clean(summary)}\n"
            f"written: {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC\n---\n\n{body.strip()}\n",
            encoding="utf-8",
        )
        self.load()
        return {"slug": slug, "path": str(f)}


_WIKI: Wiki | None = None


def get_wiki() -> Wiki:
    global _WIKI
    if _WIKI is None:
        _WIKI = Wiki()
    return _WIKI


FARM_PAGES = {
    "wash": "farms/wash-loops",
    "flat_loop": "farms/wash-loops",
    "zero_reserve": "farms/zero-reserve-pools",
    "feefarm": "farms/fee-farming",
    "roundtrip": "farms/inorganic-volume",
    "thin_crowd": "farms/inorganic-volume",
    "manual": "farms/overview",
}
DEX_PAGES = {
    "pumpfun": "launchpads/pump-fun",
    "pump": "launchpads/pump-fun",
    "pumpswap": "launchpads/pumpswap",
    "pump-amm": "launchpads/pumpswap",
    "raydium-launchlab": "launchpads/bonk-fun",
    "launchlab": "launchpads/bonk-fun",
    "bonk": "launchpads/bonk-fun",
    "meteora": "launchpads/meteora-dbc",
    "meteoradbc": "launchpads/meteora-dbc",
    "meteora-dbc": "launchpads/meteora-dbc",
    "moonshot": "launchpads/moonshot",
}


def refs_for_audit(res: dict) -> list[dict]:
    w = get_wiki()
    slugs: list[str] = []
    key = res.get("verdict_key")
    farm = res.get("farm") or {}
    if farm.get("kind"):
        slugs.append(FARM_PAGES.get(farm["kind"], "farms/overview"))
    elif farm.get("warnings"):
        slugs.append("farms/overview")
    safety = res.get("safety") or {}
    if key == "FAKE":
        slugs.append("rugs/copycat-impersonation")
    if key == "HONEYPOT" or safety.get("freeze_authority"):
        slugs.append("rugs/freeze-honeypot")
    if safety.get("is_token_2022"):
        slugs.append("rugs/token-2022-traps")
    if safety.get("mint_authority"):
        slugs.append("rugs/mint-authority")
    if key == "HIGH_RISK":
        slugs.append("rugs/liquidity-pull")
    top10 = (res.get("holders") or {}).get("top10_pct")
    if top10 and top10 > 40:
        slugs.append("rugs/bundled-supply")
    dex = ((res.get("market") or {}).get("dex") or "").lower()
    if dex in DEX_PAGES:
        slugs.append(DEX_PAGES[dex])
    out, seen = [], set()
    for s in slugs:
        p = w.pages.get(s)
        if p and s not in seen:
            seen.add(s)
            out.append({"slug": s, "title": p["title"]})
    return out[:4]


def write_postmortem(db, signal_id: int) -> dict | None:
    """When a tracked signal dies or rugs, write a short code-generated case page (no LLM)."""
    s = db.conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    if not s or s["status"] not in ("dead", "rugged"):
        return None
    s = dict(s)
    marks = db.conn.execute(
        "SELECT ts, fdv, liq FROM signal_marks WHERE signal_id=? ORDER BY ts", (signal_id,)
    ).fetchall()
    levels = [
        r["level"]
        for r in db.conn.execute("SELECT level FROM milestones WHERE signal_id=? ORDER BY level", (signal_id,))
    ]
    life_h = ((s.get("ended_at") or time.time()) - s["ts"]) / 3600
    peak = (s["peak_fdv"] / s["fdv0"]) if s.get("peak_fdv") and s.get("fdv0") else None
    sym = (s.get("symbol") or "token").lower()
    slug = f"cases/auto-{re.sub(r'[^a-z0-9]+', '-', sym).strip('-') or 'token'}-{s['mint'][:6].lower()}"
    fmt = lambda v: f"${v:,.0f}" if v else "n/a"  # noqa: E731
    body = (
        f"# {s.get('symbol')} ({s['status']})\n\n"
        f"Auto post-mortem from the signal ledger. Mint `{s['mint']}`, source `{s['source']}`, dex `{s.get('dex')}`.\n\n"
        f"- Entry verdict: **{s['verdict']}** (latest audit: {s.get('verdict_now')})\n"
        f"- Called at FDV {fmt(s.get('fdv0'))} with liquidity {fmt(s.get('liq0'))}\n"
        f"- Peak: {f'{peak:.2f}x' if peak else 'n/a'} · milestones: {', '.join(f'{x}x' for x in levels) or 'none'}\n"
        f"- Ended {s['status']} after {life_h:.1f}h at FDV {fmt(s.get('last_fdv'))}, liquidity {fmt(s.get('last_liq'))}\n"
        f"- Marks recorded: {len(marks)}\n\n"
        f"Entry reasons: {s.get('reasons')}\n\n"
        "Check against [[rugs/overview]]: was this a liquidity pull, a dev dump, bundled supply, or a farm that "
        "stopped? Edit this page with what you learn.\n"
    )
    try:
        return get_wiki().note(
            slug,
            f"{s.get('symbol')} {s['status']} (auto)",
            body,
            tags=f"case, auto, {s['status']}, {s['verdict'].lower()}",
            summary=f"{s['verdict']} call that ended {s['status']} after {life_h:.0f}h",
        )
    except Exception:  # noqa: BLE001
        return None
