"""WizzyDB: Wizzy's own tables in ~/.heavymetal/wizzy.db (SQLite, WAL).

Market history (trench_days, launches, fg_days, signals) stays in heavymetal's DB, shared through the reader env.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path

from heavymetal import paths

SCHEMA_VERSION = 1
ADDED_COLUMNS = {"scrolls": {"meta": "TEXT"}}  # columns added after v1; ALTERed into older databases

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, x_id TEXT UNIQUE, tg_id TEXT UNIQUE, tier TEXT NOT NULL DEFAULT 'free',
  tier_expires_at REAL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, key TEXT NOT NULL UNIQUE, symbol TEXT);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY, user_id INTEGER, surface TEXT, raw TEXT, intent TEXT, subject_id INTEGER,
  status TEXT, latency_ms INTEGER, cost_usd REAL DEFAULT 0, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_requests_created ON requests(created_at);
CREATE TABLE IF NOT EXISTS facts_snapshots (
  id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL, facts TEXT NOT NULL, as_of REAL NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_facts_subject ON facts_snapshots(subject_id, as_of);
CREATE TABLE IF NOT EXISTS scrolls (
  slug TEXT PRIMARY KEY, subject_id INTEGER, request_id INTEGER, kind TEXT, reading TEXT, title TEXT, body_md TEXT,
  omen TEXT, chart_urls TEXT, paywalled INTEGER DEFAULT 1, price_usdc REAL, created_at REAL NOT NULL, meta TEXT);
CREATE TABLE IF NOT EXISTS entitlements (
  id INTEGER PRIMARY KEY, user_id INTEGER, scroll_slug TEXT, method TEXT NOT NULL, tx_sig TEXT UNIQUE,
  amount REAL, expires_at REAL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rate_limits (
  user_key TEXT NOT NULL, bucket TEXT NOT NULL, window_start REAL NOT NULL, count INTEGER NOT NULL,
  PRIMARY KEY (user_key, bucket));
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0, run_after REAL NOT NULL, dedupe_key TEXT UNIQUE, result TEXT,
  last_error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_jobs_due ON jobs(status, run_after);
CREATE TABLE IF NOT EXISTS x_state (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS x_replies (
  tweet_id TEXT PRIMARY KEY, conversation_id TEXT, user_id TEXT, reply_id TEXT, replied_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_x_replies_conv ON x_replies(conversation_id, user_id);
CREATE TABLE IF NOT EXISTS prophecies (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, subject TEXT NOT NULL, claim TEXT NOT NULL,
  metric TEXT NOT NULL, op TEXT NOT NULL, threshold REAL, horizon_h REAL NOT NULL, baseline TEXT NOT NULL,
  features TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', outcome TEXT, resolved_ts REAL,
  value_at_resolve REAL, posted_text TEXT, x_post_id TEXT, tg_msg_id TEXT, public_at REAL);
CREATE INDEX IF NOT EXISTS ix_prophecies_status ON prophecies(status, ts);
CREATE TABLE IF NOT EXISTS prophecy_marks (
  id INTEGER PRIMARY KEY, prophecy_id INTEGER NOT NULL, ts REAL NOT NULL, value REAL, source TEXT);
CREATE TABLE IF NOT EXISTS scoreboards (week TEXT PRIMARY KEY, stats TEXT NOT NULL, posted_text TEXT, x_post_id TEXT,
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS watches (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL, params TEXT NOT NULL,
  chat_id TEXT NOT NULL, cooldown_s INTEGER NOT NULL DEFAULT 3600, active INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL, last_check REAL, last_fired REAL);
CREATE INDEX IF NOT EXISTS ix_watches_active ON watches(active, kind);
CREATE TABLE IF NOT EXISTS watch_snapshots (watch_id INTEGER PRIMARY KEY, ts REAL NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch_events (
  id INTEGER PRIMARY KEY, watch_id INTEGER NOT NULL, event_key TEXT NOT NULL, ts REAL NOT NULL, payload TEXT,
  delivered INTEGER NOT NULL DEFAULT 0, UNIQUE (watch_id, event_key));
CREATE TABLE IF NOT EXISTS lesson_progress (
  user_id INTEGER NOT NULL, slug TEXT NOT NULL, started_at REAL, completed_at REAL, quiz_score REAL,
  attempts INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, slug));
CREATE TABLE IF NOT EXISTS familiars (user_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, granted_at REAL NOT NULL,
  source TEXT);
CREATE TABLE IF NOT EXISTS perks (user_id INTEGER NOT NULL, flag TEXT NOT NULL, value REAL NOT NULL,
  PRIMARY KEY (user_id, flag));
CREATE TABLE IF NOT EXISTS narrative_tags (mint TEXT PRIMARY KEY, narrative TEXT NOT NULL, method TEXT NOT NULL,
  tagged_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS solana_pay_orders (
  reference TEXT PRIMARY KEY, user_id INTEGER NOT NULL, amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  tx_sig TEXT, created_at REAL NOT NULL);
"""


def wizzy_db_path() -> Path:
    return paths.home() / "wizzy.db"


class WizzyDB:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else wizzy_db_path()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._add_missing_columns()
        if self.meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        self.conn.commit()

    def _add_missing_columns(self) -> None:
        for table, cols in ADDED_COLUMNS.items():
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, typ in cols.items():
                if name not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")

    # ------------------------------------------------------------------ helpers
    def _x(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, args).fetchone()

    def all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()

    def meta(self, key: str) -> str | None:
        row = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._x(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def secret(self, name: str) -> str:
        """A random secret generated once and kept in the DB (never in config.toml)."""
        key = f"secret:{name}"
        val = self.meta(key)
        if not val:
            val = secrets.token_urlsafe(32)
            self.set_meta(key, val)
        return val

    # ------------------------------------------------------------------ users and subjects
    def user(self, *, tg_id: str | None = None, x_id: str | None = None) -> sqlite3.Row:
        """Get or create a user by Telegram or X id."""
        col, val = ("tg_id", tg_id) if tg_id is not None else ("x_id", x_id)
        if val is None:
            raise ValueError("tg_id or x_id required")
        row = self.one(f"SELECT * FROM users WHERE {col}=?", (str(val),))
        if row is None:
            self._x(f"INSERT INTO users({col}, created_at) VALUES(?, ?)", (str(val), time.time()))
            row = self.one(f"SELECT * FROM users WHERE {col}=?", (str(val),))
        return row

    def tier(self, user_id: int) -> str:
        row = self.one("SELECT tier, tier_expires_at FROM users WHERE id=?", (user_id,))
        if row is None:
            return "free"
        if row["tier"] == "inner" and (row["tier_expires_at"] or 0) < time.time():
            return "free"
        return row["tier"]

    def subject(self, kind: str, key: str, symbol: str | None = None) -> int:
        self._x(
            "INSERT INTO subjects(kind, key, symbol) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET symbol=COALESCE(excluded.symbol, subjects.symbol)",
            (kind, key, symbol),
        )
        return self.one("SELECT id FROM subjects WHERE key=?", (key,))["id"]

    # ------------------------------------------------------------------ requests
    def add_request(self, user_id: int | None, surface: str, raw: str, intent: str) -> int:
        return self._x(
            "INSERT INTO requests(user_id, surface, raw, intent, status, created_at) VALUES(?, ?, ?, ?, 'open', ?)",
            (user_id, surface, raw[:2000], intent, time.time()),
        ).lastrowid

    def finish_request(
        self, rid: int, status: str, subject_id: int | None = None, cost_usd: float = 0.0, latency_ms: int | None = None
    ) -> None:
        self._x(
            "UPDATE requests SET status=?, subject_id=COALESCE(?, subject_id), cost_usd=cost_usd+?, latency_ms=? WHERE id=?",
            (status, subject_id, cost_usd, latency_ms, rid),
        )

    def spend_since(self, ts: float) -> float:
        row = self.one("SELECT COALESCE(SUM(cost_usd), 0) AS c FROM requests WHERE created_at >= ?", (ts,))
        return float(row["c"])

    @staticmethod
    def dumps(obj) -> str:
        return json.dumps(obj, default=str, separators=(",", ":"))
