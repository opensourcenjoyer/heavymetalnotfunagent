"""SQLite storage: sessions, full message history (incl. tool calls), trades ledger, reviews, knowledge."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from heavymetal import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created_at REAL, title TEXT);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, session_id TEXT, message TEXT, created_at REAL);
CREATE INDEX IF NOT EXISTS ix_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY, ts REAL, session_id TEXT, tool TEXT, action TEXT, mint TEXT,
  amount REAL, unit TEXT, counterparty TEXT, signature TEXT, status TEXT, error TEXT, raw TEXT);
CREATE INDEX IF NOT EXISTS ix_trades_mint ON trades(mint, ts);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY, ts REAL, session_id TEXT, tool TEXT, args TEXT, verdict TEXT,
  reasons TEXT, steps TEXT, model TEXT, cost_usd REAL, latency_s REAL);
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY, ts REAL, session_id TEXT, role TEXT, model TEXT,
  input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL);
CREATE TABLE IF NOT EXISTS knowledge (id INTEGER PRIMARY KEY, ts REAL, content TEXT, tags TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(content, tags, content='knowledge', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
  INSERT INTO knowledge_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
END;
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY, opened_at REAL, closed_at REAL, session_id TEXT, mint TEXT,
  symbol TEXT, entry_price_usd REAL, token_amount REAL, sol_invested REAL, tp_multiple REAL,
  sl_pct REAL, tp_price_usd REAL, sl_price_usd REAL, status TEXT, exit_price_usd REAL,
  exit_signature TEXT, pnl_pct REAL, notes TEXT);
CREATE INDEX IF NOT EXISTS ix_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS ix_positions_mint ON positions(mint);
"""


class DB:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.db_path()
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _x(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur

    # ---------------------------------------------------------------- sessions
    def new_session(self) -> str:
        sid = uuid.uuid4().hex[:12]
        self._x("INSERT INTO sessions VALUES (?,?,?)", (sid, time.time(), ""))
        return sid

    def latest_session(self) -> str | None:
        row = self.conn.execute("SELECT id FROM sessions ORDER BY created_at DESC LIMIT 1").fetchone()
        return row["id"] if row else None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.id, s.created_at, COUNT(m.id) n FROM sessions s LEFT JOIN messages m "
            "ON m.session_id=s.id GROUP BY s.id ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_message(self, session_id: str, message: dict) -> None:
        self._x(
            "INSERT INTO messages (session_id, message, created_at) VALUES (?,?,?)",
            (session_id, json.dumps(message), time.time()),
        )

    def messages(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT message FROM messages WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
        return [json.loads(r["message"]) for r in rows]

    # ---------------------------------------------------------------- ledger
    def add_trade(
        self,
        session_id: str,
        tool: str,
        action: str,
        mint: str | None,
        amount: float | None,
        unit: str,
        counterparty: str | None,
        result: dict,
    ) -> None:
        self._x(
            "INSERT INTO trades (ts, session_id, tool, action, mint, amount, unit, counterparty, signature,"
            " status, error, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                time.time(),
                session_id,
                tool,
                action,
                mint,
                amount,
                unit,
                counterparty,
                result.get("signature"),
                result.get("status"),
                result.get("error"),
                json.dumps(result),
            ),
        )

    def trades(self, limit: int = 20, mint: str | None = None, since: float | None = None) -> list[dict]:
        sql, args = "SELECT * FROM trades WHERE 1=1", []
        if mint:
            sql += " AND mint=?"
            args.append(mint)
        if since:
            sql += " AND ts>=?"
            args.append(since)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    # ---------------------------------------------------------------- reviews
    def add_review(
        self,
        session_id: str,
        tool: str,
        args: dict,
        verdict: str,
        reasons: list,
        steps: list,
        model: str,
        cost: float,
        latency: float,
    ) -> int:
        cur = self._x(
            "INSERT INTO reviews (ts, session_id, tool, args, verdict, reasons, steps, model, cost_usd,"
            " latency_s) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                time.time(),
                session_id,
                tool,
                json.dumps(args),
                verdict,
                json.dumps(reasons),
                json.dumps(steps),
                model,
                cost,
                latency,
            ),
        )
        return cur.lastrowid

    def reviews(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- usage
    def add_usage(self, session_id: str, role: str, model: str, tin: int, tout: int, cost: float | None) -> None:
        self._x(
            "INSERT INTO usage (ts, session_id, role, model, input_tokens, output_tokens, cost_usd)"
            " VALUES (?,?,?,?,?,?,?)",
            (time.time(), session_id, role, model, tin, tout, cost),
        )

    def usage(self, session_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, model, SUM(input_tokens) tin, SUM(output_tokens) tout, SUM(cost_usd) cost, COUNT(*) calls"
            " FROM usage WHERE session_id=? GROUP BY role, model",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- knowledge
    def remember(self, content: str, tags: str = "") -> int:
        return self._x(
            "INSERT INTO knowledge (ts, content, tags) VALUES (?,?,?)", (time.time(), content, tags)
        ).lastrowid

    def recall(self, query: str, limit: int = 8) -> list[dict]:
        terms = " OR ".join(f'"{t}"' for t in query.replace('"', " ").split() if t)
        if not terms:
            return []
        try:
            rows = self.conn.execute(
                "SELECT k.id, k.content, k.tags, k.ts FROM knowledge_fts f JOIN knowledge k ON k.id=f.rowid "
                "WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?",
                (terms, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self.conn.execute(
                "SELECT id, content, tags, ts FROM knowledge WHERE content LIKE ? LIMIT ?", (f"%{query}%", limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- positions
    def add_position(
        self,
        session_id: str,
        mint: str,
        symbol: str,
        entry_price_usd: float | None,
        token_amount: float | None,
        sol_invested: float,
        tp_multiple: float | None = 2.0,
        sl_pct: float | None = 30.0,
        tp_price_usd: float | None = None,
        sl_price_usd: float | None = None,
        notes: str = "",
    ) -> int:
        cur = self._x(
            "INSERT INTO positions (opened_at, session_id, mint, symbol, entry_price_usd, token_amount, "
            "sol_invested, tp_multiple, sl_pct, tp_price_usd, sl_price_usd, status, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,'OPEN',?)",
            (
                time.time(),
                session_id,
                mint,
                symbol,
                entry_price_usd,
                token_amount,
                sol_invested,
                tp_multiple,
                sl_pct,
                tp_price_usd,
                sl_price_usd,
                notes,
            ),
        )
        return cur.lastrowid

    def open_positions(self, mint: str | None = None) -> list[dict]:
        sql = "SELECT * FROM positions WHERE status='OPEN'"
        args = []
        if mint:
            sql += " AND mint=?"
            args.append(mint)
        sql += " ORDER BY opened_at DESC"
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def close_position(
        self,
        pos_id: int,
        status: str = "CLOSED_MANUAL",
        exit_price_usd: float | None = None,
        exit_signature: str | None = None,
        pnl_pct: float | None = None,
    ) -> None:
        self._x(
            "UPDATE positions SET status=?, closed_at=?, exit_price_usd=?, exit_signature=?, pnl_pct=? WHERE id=?",
            (status, time.time(), exit_price_usd, exit_signature, pnl_pct, pos_id),
        )

    def list_positions(self, limit: int = 25, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM positions WHERE 1=1"
        args = []
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY opened_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]
