"""
Corretora simulada (paper trading).

Gera candles sintéticos realistas via passeio aleatório com volatilidade
agrupada, e resolve as ordens pelo preço na expiração aplicando o payout.
Serve para validar toda a stack sem tocar em dinheiro real nem depender
de rede — é também o que roda nos testes automatizados.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from ..core.models import AccountBalance, Direction, Order, OrderStatus
from .base import Broker

logger = logging.getLogger(__name__)


class PaperBroker(Broker):
    """Simulador determinístico (com seed) para desenvolvimento e testes."""

    name = "paper"

    def __init__(self, settings, seed: int = 42, initial_balance: float = 1000.0,
                 payout_rate: float = 0.85):
        super().__init__(settings)
        self._rng = np.random.default_rng(seed)
        self._balance = initial_balance
        self._payout = payout_rate
        self._series: dict[str, pd.DataFrame] = {}
        self._pending: dict[str, Order] = {}

    # ---- Ciclo de vida -------------------------------------------------

    def connect(self) -> bool:
        self._connected = True
        logger.info("[paper] conectado | saldo simulado $%.2f", self._balance)
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("[paper] desconectado")

    def health_check(self) -> bool:
        return self._connected

    # ---- Dados ---------------------------------------------------------

    def _generate_series(self, symbol: str, count: int, timeframe_minutes: int) -> pd.DataFrame:
        """Passeio aleatório com volatilidade agrupada (efeito GARCH simplificado)."""
        n = max(count, 400)
        base_price = 1.1000 if "EUR" in symbol.upper() else 100.0

        # Volatilidade que persiste no tempo, como em mercado real
        vol = np.zeros(n)
        vol[0] = 0.0006
        for i in range(1, n):
            vol[i] = 0.90 * vol[i - 1] + 0.10 * abs(self._rng.normal(0, 0.0008))
        vol = np.clip(vol, 0.0002, 0.004)

        returns = self._rng.normal(0, 1, n) * vol
        # Leve reversão à média, típica de intraday
        for i in range(1, n):
            returns[i] -= 0.05 * returns[i - 1]

        close = base_price * np.exp(np.cumsum(returns))
        open_ = np.concatenate([[base_price], close[:-1]])
        spread = vol * base_price * 1.5
        high = np.maximum(open_, close) + np.abs(self._rng.normal(0, 1, n)) * spread
        low = np.minimum(open_, close) - np.abs(self._rng.normal(0, 1, n)) * spread
        volume = self._rng.integers(100, 1000, n).astype(float)

        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        timestamps = [end - timedelta(minutes=timeframe_minutes * (n - 1 - i)) for i in range(n)]

        return pd.DataFrame({
            "timestamp": timestamps, "open": open_, "high": high,
            "low": low, "close": close, "volume": volume,
        })

    def get_candles(self, symbol: str, timeframe_minutes: int, count: int) -> pd.DataFrame:
        key = f"{symbol}_{timeframe_minutes}"
        if key not in self._series:
            self._series[key] = self._generate_series(symbol, count, timeframe_minutes)
        else:
            # Avança um candle a cada chamada, simulando o tempo passando
            df = self._series[key]
            last = df.iloc[-1]
            step = float(self._rng.normal(0, 0.0008)) * last["close"]
            new_close = max(last["close"] + step, 0.0001)
            new_row = {
                "timestamp": last["timestamp"] + timedelta(minutes=timeframe_minutes),
                "open": last["close"],
                "high": max(last["close"], new_close) * (1 + abs(self._rng.normal(0, 0.0003))),
                "low": min(last["close"], new_close) * (1 - abs(self._rng.normal(0, 0.0003))),
                "close": new_close,
                "volume": float(self._rng.integers(100, 1000)),
            }
            self._series[key] = pd.concat(
                [df, pd.DataFrame([new_row])], ignore_index=True
            ).tail(1000).reset_index(drop=True)

        return self.normalize_candles(self._series[key].tail(count))

    def get_balance(self) -> AccountBalance:
        return AccountBalance(balance=round(self._balance, 2), currency="USD", mode="paper")

    def payout(self, symbol: str) -> float:
        return self._payout

    def min_stake(self) -> float:
        return 1.0

    # ---- Execução ------------------------------------------------------

    def place_order(
        self, symbol: str, direction: Direction, amount: float, expiration_minutes: int
    ) -> Order:
        candles = self.get_candles(symbol, self.settings.timeframe_minutes, 5)
        entry_price = float(candles["close"].iloc[-1])

        order = Order(
            symbol=symbol, direction=direction, amount=amount,
            expiration_minutes=expiration_minutes, entry_price=entry_price,
            status=OrderStatus.OPEN, dry_run=True,
        )
        order.broker_order_id = f"paper-{order.id[:8]}"
        order.metadata["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)
        ).isoformat()

        self._balance -= amount
        self._pending[order.id] = order
        logger.info("[paper] ordem %s %s $%.2f @ %.5f",
                    order.broker_order_id, direction.value, amount, entry_price)
        return order

    def check_order(self, order: Order) -> Order:
        """Resolve a ordem se a expiração já passou."""
        if order.is_closed:
            return order

        expires_at = order.metadata.get("expires_at")
        if expires_at and datetime.now(timezone.utc) < datetime.fromisoformat(expires_at):
            return order  # ainda aberta

        candles = self.get_candles(order.symbol, self.settings.timeframe_minutes, 5)
        exit_price = float(candles["close"].iloc[-1])
        order.exit_price = exit_price
        order.closed_at = datetime.now(timezone.utc)

        entry = order.entry_price or exit_price
        if exit_price == entry:
            order.status = OrderStatus.TIE
            order.profit = 0.0
            self._balance += order.amount
        else:
            went_up = exit_price > entry
            won = (order.direction is Direction.CALL) == went_up
            if won:
                order.status = OrderStatus.WON
                order.profit = order.amount * self._payout
                self._balance += order.amount + order.profit
            else:
                order.status = OrderStatus.LOST
                order.profit = -order.amount

        self._pending.pop(order.id, None)
        logger.info("[paper] ordem %s -> %s | PnL $%.2f | saldo $%.2f",
                    order.broker_order_id, order.status.value, order.profit, self._balance)
        return order
