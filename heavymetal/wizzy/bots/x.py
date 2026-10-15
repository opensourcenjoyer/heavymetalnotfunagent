"""X surface: poll mentions (since_id), reply through the job queue with delays and caps.

Rules followed (X automation policy): reply only to mentions, never DM, never reply twice to one user in a thread,
per-user and daily caps, randomized delay. Mark the account as automated in X settings.
"""

from __future__ import annotations

import asyncio
import random
import re
import time

from heavymetal.wizzy import jobs, limits
from heavymetal.wizzy.bots.core import Reply, handle_text
from heavymetal.wizzy.writer import FOOTER
from heavymetal.worker import BackgroundWorker

TCO_LEN = 23  # every URL counts as 23 characters on X
MAX_LEN = 280
# PDF section 8 cost guide (USD per call), adjust to your X developer plan.
COST_MENTIONS_READ = 0.005
COST_POST = 0.015
MENTION_RE = re.compile(r"(^|\s)@\w{1,15}")


class XClient:
    """Thin async wrapper over tweepy so tests can swap in a fake."""

    def __init__(self, keys):
        from tweepy.asynchronous import AsyncClient

        self.user_id = keys.x_user_id
        self.c = AsyncClient(
            bearer_token=keys.x_bearer_token or None,
            consumer_key=keys.x_api_key or None,
            consumer_secret=keys.x_api_secret or None,
            access_token=keys.x_access_token or None,
            access_token_secret=keys.x_access_secret or None,
        )

    async def mentions(self, since_id: str | None) -> list[dict]:
        params = {"tweet_fields": ["conversation_id", "author_id", "created_at"], "max_results": 50}
        if since_id:
            params["since_id"] = since_id
        resp = await self.c.get_users_mentions(self.user_id, **params)
        return [
            {"id": str(t.id), "text": t.text, "author_id": str(t.author_id), "conversation_id": str(t.conversation_id)}
            for t in resp.data or []
        ]

    async def reply(self, text: str, in_reply_to: str) -> str:
        resp = await self.c.create_tweet(text=text, in_reply_to_tweet_id=in_reply_to)
        return str((resp.data or {}).get("id", ""))

    async def post(self, text: str) -> str:
        resp = await self.c.create_tweet(text=text)
        return str((resp.data or {}).get("id", ""))


def x_ready(keys) -> bool:
    return all(
        [
            keys.x_user_id,
            keys.x_bearer_token,
            keys.x_api_key,
            keys.x_api_secret,
            keys.x_access_token,
            keys.x_access_secret,
        ]
    )


def strip_mentions(text: str) -> str:
    return MENTION_RE.sub(" ", text or "").strip()


def _visible_len(text: str) -> int:
    return len(re.sub(r"https?://\S+", "x" * TCO_LEN, text))


def render_x(reply: Reply) -> str:
    """Fit a reply into one post: the reading's first sentences, the scroll link, a short disclaimer."""
    body = (reply.text or "").replace(FOOTER, "").strip()
    tail = "\nNFA · DYOR"
    link = f"\n📜 {reply.url}" if reply.url and reply.url.startswith("https://") else ""
    budget = MAX_LEN - _visible_len(link + tail) - 2
    if _visible_len(body) > budget:
        sentences = re.split(r"(?<=[.!?])\s+", body)
        out = ""
        for s in sentences:
            if _visible_len(f"{out} {s}".strip()) > budget:
                break
            out = f"{out} {s}".strip()
        body = out or body[: budget - 1].rstrip() + "…"
    return f"{body}{link}{tail}"


def record_cost(wdb, label: str, usd: float) -> None:
    rid = wdb.add_request(None, "x_api", label, "x_api")
    wdb.finish_request(rid, "api", cost_usd=usd)


async def poll_once(ctx, client) -> int:
    """Fetch new mentions and enqueue replies. Returns how many replies were queued."""
    w = ctx.wcfg
    since = ctx.wdb.one("SELECT value FROM x_state WHERE key='since_id'")
    tweets = await client.mentions(since["value"] if since else None)
    record_cost(ctx.wdb, "mentions", COST_MENTIONS_READ * max(1, len(tweets)))
    if not tweets:
        return 0
    queued = 0
    for t in sorted(tweets, key=lambda t: int(t["id"])):
        if t["author_id"] == str(client.user_id):
            continue
        if ctx.wdb.one("SELECT 1 FROM x_replies WHERE tweet_id=?", (t["id"],)):
            continue
        if ctx.wdb.one(
            "SELECT 1 FROM x_replies WHERE conversation_id=? AND user_id=?", (t["conversation_id"], t["author_id"])
        ):
            continue  # one reply per user per thread
        if not limits.hit(ctx.wdb, f"x{t['author_id']}", "x_user_day", 5, 86400).allowed:
            continue
        if not limits.hit(ctx.wdb, "x", "x_reply_day", w.x_daily_reply_cap, 86400).allowed:
            break
        delay = random.uniform(w.x_reply_delay_s, 2 * w.x_reply_delay_s)
        if jobs.enqueue(ctx.wdb, "x_reply", t, dedupe_key=f"x:{t['id']}", run_after=time.time() + delay):
            queued += 1
    newest = max(tweets, key=lambda t: int(t["id"]))["id"]
    ctx.wdb._x(
        "INSERT INTO x_state(key, value) VALUES('since_id', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (newest,),
    )
    return queued


async def handle_reply_job(ctx, client, payload: dict) -> dict:
    if ctx.wdb.one("SELECT 1 FROM x_replies WHERE tweet_id=?", (payload["id"],)):
        return {"skipped": "already replied"}
    uid = ctx.wdb.user(x_id=payload["author_id"])["id"]
    reply = await handle_text(
        ctx, uid, strip_mentions(payload["text"]), surface="x", is_group=True, chat_key=f"x{payload['author_id']}"
    )
    if reply is None or reply.kind in ("limited", "chitchat"):
        # On X, stay quiet rather than post canned lines; readings, omens and refusals are worth a reply.
        return {"skipped": reply.kind if reply else "flood"}
    text = render_x(reply)
    rid = await client.reply(text, payload["id"])
    record_cost(ctx.wdb, "post", COST_POST)
    ctx.wdb._x(
        "INSERT OR IGNORE INTO x_replies(tweet_id, conversation_id, user_id, reply_id, replied_at) VALUES(?,?,?,?,?)",
        (payload["id"], payload["conversation_id"], payload["author_id"], rid, time.time()),
    )
    return {"reply_id": rid}


class XPoller(BackgroundWorker):
    name = "wizzy-x"

    def __init__(self, ctx, client, on_alert=None):
        super().__init__(ctx.env, on_alert)
        self.ctx = ctx
        self.client = client

    def can_start(self) -> bool:
        if not self.ctx.wcfg.x_enabled:
            self.last_error = "x disabled (wizzy.x_enabled=false)"
            return False
        return True

    def loops(self):
        return (self._loop,)

    async def _loop(self) -> None:
        while True:
            await poll_once(self.ctx, self.client)
            await asyncio.sleep(max(60, self.ctx.wcfg.x_poll_interval_s))
