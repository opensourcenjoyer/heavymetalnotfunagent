"""Scrolls: saved readings with a public page (/s/<slug>) and a paywalled full body (/s/<slug>/full)."""

from __future__ import annotations

import re
import secrets
import sqlite3
import time
from dataclasses import dataclass


def make_slug(label: str | None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (label or "scroll").lower()).strip("-")[:24] or "scroll"
    return f"{base}-{secrets.token_hex(3)}"


@dataclass
class Scroll:
    slug: str
    kind: str
    title: str
    reading: str
    body_md: str
    omen: str | None
    subject_id: int | None
    chart_urls: list[str]
    paywalled: bool
    price_usdc: float | None
    created_at: float
    meta: dict

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> Scroll:
        import json

        return cls(
            slug=r["slug"],
            kind=r["kind"] or "token",
            title=r["title"] or "",
            reading=r["reading"] or "",
            body_md=r["body_md"] or "",
            omen=r["omen"],
            subject_id=r["subject_id"],
            chart_urls=json.loads(r["chart_urls"] or "[]"),
            paywalled=bool(r["paywalled"]),
            price_usdc=r["price_usdc"],
            created_at=r["created_at"],
            meta=json.loads(r["meta"] or "{}") if "meta" in r.keys() else {},
        )


def save(
    wdb,
    *,
    label: str | None,
    kind: str,
    title: str,
    reading: str,
    body_md: str,
    omen: str | None,
    subject_id: int | None,
    request_id: int | None,
    chart_urls: list[str] | None = None,
    paywalled: bool = True,
    price_usdc: float | None = None,
    meta: dict | None = None,
) -> str:
    slug = make_slug(label)
    wdb._x(
        "INSERT INTO scrolls(slug, subject_id, request_id, kind, reading, title, body_md, omen, chart_urls, paywalled, "
        "price_usdc, created_at, meta) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            slug,
            subject_id,
            request_id,
            kind,
            reading,
            title,
            body_md,
            omen,
            wdb.dumps(chart_urls or []),
            int(paywalled),
            price_usdc,
            time.time(),
            wdb.dumps(meta or {}),
        ),
    )
    return slug


def get(wdb, slug: str) -> Scroll | None:
    r = wdb.one("SELECT * FROM scrolls WHERE slug=?", (slug,))
    return Scroll.from_row(r) if r else None


def recent_for_subject(wdb, subject_id: int, kind: str, max_age_s: float) -> Scroll | None:
    r = wdb.one(
        "SELECT * FROM scrolls WHERE subject_id=? AND kind=? AND created_at>=? ORDER BY created_at DESC LIMIT 1",
        (subject_id, kind, time.time() - max_age_s),
    )
    return Scroll.from_row(r) if r else None


def public_url(base_url: str, slug: str) -> str:
    return f"{base_url.rstrip('/')}/s/{slug}"
