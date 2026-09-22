"""
Persistência em SQLite.

O projeto original guardava estado em JSON reescrito inteiro a cada
atualização — sem transação, sem histórico confiável e com corrupção
garantida se o processo morresse no meio da escrita. Aqui usamos SQLite
com WAL, que é atômico, concorrente e consultável.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .models import Order, OrderStatus

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id                 TEXT PRIMARY KEY,
    broker_order_id    TEXT,
    symbol             TEXT NOT NULL,
    direction          TEXT NOT NULL,
    amount             REAL NOT NULL,
    status             TEXT NOT NULL,
    entry_price        REAL,
    exit_price         REAL,
    profit             REAL DEFAULT 0,
    opened_at          TEXT NOT NULL,
    closed_at          TEXT,
    strategy           TEXT,
    confidence         REAL,
    reason             TEXT,
    dry_run            INTEGER DEFAULT 0,
    metadata           TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_opened  ON orders(opened_at);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_symbol  ON orders(symbol);

CREATE TABLE IF NOT EXISTS equity_curve (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    balance   REAL NOT NULL,
    daily_pnl REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_curve(ts);

CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    level    TEXT NOT NULL,
    category TEXT NOT NULL,
    message  TEXT NOT NULL,
    payload  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
"""


class Storage:
    """Camada de acesso a dados, thread-safe."""

    def __init__(self, db_path: str | Path):
        if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                yield conn
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ---- Ordens --------------------------------------------------------

    def save_order(self, order: Order) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    id, broker_order_id, symbol, direction, amount, status,
                    entry_price, exit_price, profit, opened_at, closed_at,
                    strategy, confidence, reason, dry_run, metadata
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    broker_order_id=excluded.broker_order_id,
                    status=excluded.status,
                    exit_price=excluded.exit_price,
                    profit=excluded.profit,
                    closed_at=excluded.closed_at,
                    reason=excluded.reason,
                    metadata=excluded.metadata
                """,
                (
                    order.id, order.broker_order_id, order.symbol,
                    order.direction.value, order.amount, order.status.value,
                    order.entry_price, order.exit_price, order.profit,
                    order.opened_at.isoformat(),
                    order.closed_at.isoformat() if order.closed_at else None,
                    order.strategy, order.confidence, order.reason,
                    int(order.dry_run), json.dumps(order.metadata, default=str),
                ),
            )

    def recent_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY opened_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def open_orders(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE status IN ('pending','open') ORDER BY opened_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def daily_summary(self, days: int = 30) -> list[dict[str, Any]]:
        """Agregado por dia — base dos gráficos do painel."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT date(opened_at) AS day,
                       COUNT(*)                                   AS trades,
                       SUM(CASE WHEN status='won'  THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) AS losses,
                       ROUND(SUM(profit), 2)                      AS pnl
                FROM orders
                WHERE status IN ('won','lost','tie')
                GROUP BY day
                ORDER BY day DESC
                LIMIT ?
                """,
                (days,),
            ).fetchall()
        return [dict(r) for r in rows]

    def strategy_performance(self) -> list[dict[str, Any]]:
        """Performance por estratégia — permite desligar o que não funciona."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT strategy,
                       COUNT(*)                                       AS trades,
                       SUM(CASE WHEN status='won' THEN 1 ELSE 0 END)  AS wins,
                       ROUND(SUM(profit), 2)                          AS pnl,
                       ROUND(AVG(confidence), 3)                      AS avg_confidence
                FROM orders
                WHERE status IN ('won','lost','tie')
                GROUP BY strategy
                ORDER BY pnl DESC
                """
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["win_rate"] = round(d["wins"] / d["trades"] * 100, 2) if d["trades"] else 0.0
            out.append(d)
        return out

    # ---- Curva de equity -----------------------------------------------

    def record_equity(self, balance: float, daily_pnl: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO equity_curve (ts, balance, daily_pnl) VALUES (?,?,?)",
                (datetime.now(timezone.utc).isoformat(), balance, daily_pnl),
            )

    def equity_curve(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ts, balance, daily_pnl FROM equity_curve ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---- Eventos -------------------------------------------------------

    def log_event(self, level: str, category: str, message: str,
                  payload: Optional[dict] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events (ts, level, category, message, payload) VALUES (?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(), level, category, message,
                    json.dumps(payload, default=str) if payload else None,
                ),
            )

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- Recuperação de estado -----------------------------------------

    def today_pnl(self) -> tuple[float, int]:
        """(PnL do dia, número de trades) — usado para retomar após restart."""
        today = date.today().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(profit), 0) AS pnl, COUNT(*) AS n
                FROM orders
                WHERE date(opened_at) = ? AND status IN ('won','lost','tie')
                """,
                (today,),
            ).fetchone()
        return float(row["pnl"]), int(row["n"])
