"""Apprentice mode: short lessons with quizzes; ranks come from lessons passed, never from message counts.

Lessons are bundled pages in heavymetal/wiki/lessons/*.md (front matter: title, summary, order; a ```quiz block
in the body). They load from the bundled package only, so a local user page can never replace one.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from importlib import resources

from heavymetal.kb.wiki import parse

PASS_SCORE = 0.66
RANKS = [(0, "Apprentice"), (3, "Adept"), (6, "Conjurer"), (9, "Sorcerer")]  # Archmage: all passed, all perfect
QUIZ_RE = re.compile(r"```quiz\n(.*?)```", re.S)


@dataclass
class Question:
    text: str
    options: list[str]
    answer: int


@dataclass
class Lesson:
    slug: str
    title: str
    summary: str
    order: int
    body: str
    quiz: list[Question] = field(default_factory=list)


def parse_quiz(block: str) -> list[Question]:
    out: list[Question] = []
    for chunk in re.split(r"\n\s*\n", block.strip()):
        lines = [ln.strip() for ln in chunk.strip().splitlines() if ln.strip()]
        if not lines or not lines[0].startswith("Q:"):
            continue
        opts, answer = [], -1
        for ln in lines[1:]:
            m = re.match(r"-\s*\[( |x|X)\]\s*(.+)", ln)
            if m:
                if m.group(1).lower() == "x":
                    answer = len(opts)
                opts.append(m.group(2).strip())
        if opts and answer >= 0:
            out.append(Question(lines[0][2:].strip(), opts, answer))
    return out


_CACHE: list[Lesson] | None = None


def lessons() -> list[Lesson]:
    global _CACHE
    if _CACHE is None:
        root = resources.files("heavymetal").joinpath("wiki/lessons")
        items = []
        for f in root.iterdir():
            if not f.name.endswith(".md"):
                continue
            meta, body = parse(f.read_text(encoding="utf-8"))
            m = QUIZ_RE.search(body)
            quiz = parse_quiz(m.group(1)) if m else []
            items.append(
                Lesson(
                    slug=f"lessons/{f.name[:-3]}",
                    title=meta.get("title") or f.name[:-3],
                    summary=meta.get("summary", ""),
                    order=int(meta.get("order") or 99),
                    body=QUIZ_RE.sub("", body).strip(),
                    quiz=quiz,
                )
            )
        _CACHE = sorted(items, key=lambda x: (x.order, x.slug))
    return _CACHE


def get(slug: str) -> Lesson | None:
    slug = slug if slug.startswith("lessons/") else f"lessons/{slug}"
    return next((x for x in lessons() if x.slug == slug), None)


# ---------------------------------------------------------------------- progress
def passed_slugs(wdb, user_id: int) -> set[str]:
    rows = wdb.all("SELECT slug FROM lesson_progress WHERE user_id=? AND completed_at IS NOT NULL", (user_id,))
    return {r["slug"] for r in rows}


def next_lesson(wdb, user_id: int) -> Lesson | None:
    done = passed_slugs(wdb, user_id)
    return next((x for x in lessons() if x.slug not in done), None)


def start(wdb, user_id: int, slug: str) -> None:
    wdb._x(
        "INSERT INTO lesson_progress(user_id, slug, started_at) VALUES(?,?,?) ON CONFLICT(user_id, slug) DO NOTHING",
        (user_id, slug, time.time()),
    )


def record_quiz(wdb, user_id: int, slug: str, correct: int, total: int) -> bool:
    """Store a quiz attempt; returns True if it passed. A pass is kept even if a later attempt scores lower."""
    score = correct / total if total else 0.0
    passed = score >= PASS_SCORE
    start(wdb, user_id, slug)
    wdb._x(
        "UPDATE lesson_progress SET attempts=attempts+1, quiz_score=MAX(COALESCE(quiz_score, 0), ?), "
        "completed_at=CASE WHEN completed_at IS NULL AND ? THEN ? ELSE completed_at END WHERE user_id=? AND slug=?",
        (score, int(passed), time.time(), user_id, slug),
    )
    return passed


@dataclass
class Rank:
    name: str
    passed: int
    total: int
    next_name: str | None
    needed: int


def rank(wdb, user_id: int) -> Rank:
    rows = wdb.all(
        "SELECT slug, quiz_score FROM lesson_progress WHERE user_id=? AND completed_at IS NOT NULL", (user_id,)
    )
    total = len(lessons())
    n = len(rows)
    if total and n >= total and all((r["quiz_score"] or 0) >= 1.0 for r in rows):
        return Rank("Archmage", n, total, None, 0)
    name = "Apprentice"
    for threshold, rname in RANKS:
        if n >= threshold:
            name = rname
    later = [(t, r) for t, r in RANKS if t > n]
    if later:
        return Rank(name, n, total, later[0][1], later[0][0] - n)
    return Rank(name, n, total, "Archmage", total - n if n < total else 0)


# ---------------------------------------------------------------------- suggestions from readings
def suggest_for(facts) -> Lesson | None:
    """The most relevant lesson for what a reading found (like kb.wiki.refs_for_audit)."""
    t = getattr(facts, "token", None)
    if t is None:
        return get("holder-concentration") if getattr(facts, "wallet", None) else None
    if t.authorities.freeze or t.authorities.mint:
        return get("authorities")
    if t.farm.isFarm:
        return get("farms")
    if t.lpLockedPct is not None and t.lpLockedPct < 50:
        return get("lp-lock")
    if t.holders.top10Pct is not None and t.holders.top10Pct > 50:
        return get("holder-concentration")
    if t.liquidityUsd is not None and t.liquidityUsd < 20_000:
        return get("liquidity")
    if t.fdvUsd and t.mcapUsd and t.fdvUsd > 2 * t.mcapUsd:
        return get("market-cap-vs-fdv")
    return None
