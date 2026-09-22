"""Modelos de domínio compartilhados por corretoras, estratégias e backtest."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class Direction(str, Enum):
    CALL = "CALL"   # compra / alta
    PUT = "PUT"     # venda / baixa
    NONE = "NONE"   # sem sinal

    @property
    def opposite(self) -> "Direction":
        if self is Direction.CALL:
            return Direction.PUT
        if self is Direction.PUT:
            return Direction.CALL
        return Direction.NONE


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    TIE = "tie"
    REJECTED = "rejected"
    ERROR = "error"


class BotState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    HALTED = "halted"   # travado pelo risk manager


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Candle:
    """Candle OHLCV normalizado — mesma forma para qualquer corretora."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low


@dataclass(slots=True)
class Signal:
    """Sinal produzido por uma estratégia, com confiança e rastreabilidade."""

    direction: Direction
    confidence: float = 0.0          # 0.0 a 1.0
    strategy: str = "unknown"
    reason: str = ""
    indicators: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def is_actionable(self) -> bool:
        return self.direction is not Direction.NONE and self.confidence > 0

    @classmethod
    def none(cls, strategy: str = "unknown", reason: str = "sem setup") -> "Signal":
        return cls(direction=Direction.NONE, confidence=0.0, strategy=strategy, reason=reason)


@dataclass(slots=True)
class Order:
    """Ordem enviada à corretora."""

    symbol: str
    direction: Direction
    amount: float
    expiration_minutes: int
    id: str = field(default_factory=lambda: str(uuid4()))
    broker_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    profit: float = 0.0
    opened_at: datetime = field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None
    strategy: str = "unknown"
    confidence: float = 0.0
    reason: str = ""
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_closed(self) -> bool:
        return self.status in (
            OrderStatus.WON, OrderStatus.LOST, OrderStatus.TIE,
            OrderStatus.REJECTED, OrderStatus.ERROR,
        )

    @property
    def is_win(self) -> bool:
        return self.status is OrderStatus.WON

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "amount": round(self.amount, 2),
            "status": self.status.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "profit": round(self.profit, 2),
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "strategy": self.strategy,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "dry_run": self.dry_run,
        }


@dataclass(slots=True)
class AccountBalance:
    balance: float
    currency: str = "USD"
    mode: str = "demo"
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class PerformanceStats:
    """Métricas de performance calculadas a partir do histórico de ordens."""

    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    current_streak: int = 0        # positivo = vitórias, negativo = derrotas
    max_win_streak: int = 0
    max_loss_streak: int = 0
    equity_peak: float = 0.0

    @property
    def win_rate(self) -> float:
        decided = self.wins + self.losses
        return (self.wins / decided * 100) if decided else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss == 0:
            return float("inf") if self.gross_profit > 0 else 0.0
        return self.gross_profit / abs(self.gross_loss)

    @property
    def expectancy(self) -> float:
        """Resultado médio esperado por trade."""
        return self.net_profit / self.total_trades if self.total_trades else 0.0

    def to_dict(self) -> dict[str, Any]:
        pf = self.profit_factor
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "win_rate": round(self.win_rate, 2),
            "net_profit": round(self.net_profit, 2),
            "gross_profit": round(self.gross_profit, 2),
            "gross_loss": round(self.gross_loss, 2),
            "profit_factor": round(pf, 2) if pf != float("inf") else None,
            "expectancy": round(self.expectancy, 4),
            "max_drawdown": round(self.max_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "current_streak": self.current_streak,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
        }
