"""Persistencia en SQLite: posiciones, operaciones, equity y estado clave-valor.

Todo lo necesario para que el bot sepa qué tiene tras un reinicio vive aquí.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY, qty REAL NOT NULL, entry_price REAL NOT NULL,
    entry_fee REAL NOT NULL, stop REAL NOT NULL, opened_at REAL NOT NULL,
    stop_order_id TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL,
    pnl REAL, reason TEXT, client_id TEXT
);
CREATE TABLE IF NOT EXISTS equity (ts REAL PRIMARY KEY, equity REAL NOT NULL);
"""


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_fee: float
    stop: float
    opened_at: float
    stop_order_id: str | None = None


@dataclass
class Trade:
    ts: float
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    pnl: float | None = None
    reason: str = ""
    client_id: str | None = None


class State:
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # --- clave-valor -------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def get_float(self, key: str, default: float) -> float:
        value = self.get(key)
        return float(value) if value is not None else default

    def get_json(self, key: str, default=None):
        value = self.get(key)
        return json.loads(value) if value is not None else default

    def set(self, key: str, value) -> None:
        if not isinstance(value, str):
            value = json.dumps(value)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, value))

    def delete(self, key: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM kv WHERE key=?", (key,))

    # --- posiciones y operaciones -----------------------------------------
    def positions(self) -> dict[str, Position]:
        rows = self.db.execute(
            "SELECT symbol, qty, entry_price, entry_fee, stop, opened_at, stop_order_id FROM positions"
        ).fetchall()
        return {r[0]: Position(*r) for r in rows}

    def save_position(self, pos: Position) -> None:
        with self.db:
            self._upsert(pos)

    def open_position(self, pos: Position, trade: Trade) -> None:
        with self.db:  # posición y operación en la misma transacción
            self._upsert(pos)
            self._insert_trade(trade)

    def close_position(self, symbol: str, trade: Trade) -> None:
        with self.db:
            self.db.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
            self._insert_trade(trade)

    def trades(self, limit: int = 50) -> list[Trade]:
        rows = self.db.execute(
            "SELECT ts, symbol, side, qty, price, fee, pnl, reason, client_id FROM trades ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Trade(*r) for r in rows]

    def record_equity(self, ts: float, equity: float) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO equity(ts, equity) VALUES (?, ?)", (ts, equity))

    def _upsert(self, pos: Position) -> None:
        d = asdict(pos)
        self.db.execute(
            "INSERT OR REPLACE INTO positions(symbol, qty, entry_price, entry_fee, stop, opened_at, stop_order_id) "
            "VALUES (:symbol, :qty, :entry_price, :entry_fee, :stop, :opened_at, :stop_order_id)",
            d,
        )

    def _insert_trade(self, t: Trade) -> None:
        self.db.execute(
            "INSERT INTO trades(ts, symbol, side, qty, price, fee, pnl, reason, client_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t.ts, t.symbol, t.side, t.qty, t.price, t.fee, t.pnl, t.reason, t.client_id),
        )
