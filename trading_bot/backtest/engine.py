"""
Backtester para opções binárias.

Esta é a peça mais importante que faltava. Sem backtest, a escolha de
estratégia era um chute — e o log do robô antigo mostra exatamente o
resultado disso: 38,5% de acerto em 26 operações.

Matemática que o backtest torna explícita:
  com payout p, o ponto de equilíbrio exige acerto de 1/(1+p).
  Payout 85% => precisa de 54,05% de acerto só para empatar.
  Payout 80% => precisa de 55,56%.
Uma estratégia com 50% de acerto perde dinheiro de forma garantida.

Premissas conservadoras adotadas aqui:
  * Entrada no OPEN do candle seguinte ao sinal (nunca no close do
    candle que gerou o sinal — isso seria look-ahead bias).
  * Resultado apurado no CLOSE do candle de expiração.
  * Empate (close idêntico) conta como devolução da aposta.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..core import indicators
from ..core.models import Direction, PerformanceStats
from ..core.strategies import get_strategy

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    direction: str
    entry_price: float
    exit_price: float
    stake: float
    profit: float
    result: str
    confidence: float
    reason: str


@dataclass(slots=True)
class BacktestResult:
    """Resultado completo, pronto para serializar no painel."""

    strategy: str
    symbol: str
    payout: float
    initial_balance: float
    final_balance: float
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    stats: PerformanceStats = field(default_factory=PerformanceStats)
    breakeven_win_rate: float = 0.0
    candles_tested: int = 0

    @property
    def is_profitable(self) -> bool:
        return self.final_balance > self.initial_balance

    @property
    def edge(self) -> float:
        """Vantagem em pontos percentuais sobre o ponto de equilíbrio."""
        return self.stats.win_rate - self.breakeven_win_rate

    def summary(self) -> dict[str, Any]:
        ret_pct = (
            (self.final_balance - self.initial_balance) / self.initial_balance * 100
            if self.initial_balance else 0.0
        )
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "payout": self.payout,
            "candles_tested": self.candles_tested,
            "initial_balance": round(self.initial_balance, 2),
            "final_balance": round(self.final_balance, 2),
            "return_pct": round(ret_pct, 2),
            "breakeven_win_rate": round(self.breakeven_win_rate, 2),
            "edge_pp": round(self.edge, 2),
            "profitable": self.is_profitable,
            "verdict": self._verdict(),
            **self.stats.to_dict(),
        }

    def _verdict(self) -> str:
        if self.stats.total_trades < 30:
            return "amostra insuficiente — não confie neste resultado"
        if self.edge <= 0:
            return "REPROVADA: abaixo do ponto de equilíbrio, perde dinheiro no longo prazo"
        if self.edge < 2:
            return "MARGINAL: vantagem dentro do ruído estatístico"
        if self.stats.max_drawdown_pct > 30:
            return "ARRISCADA: lucrativa, mas com drawdown alto demais"
        return "APROVADA: vantagem positiva com drawdown controlado"

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "equity_curve": [round(v, 2) for v in self.equity_curve],
            "trades": [
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "direction": t.direction,
                    "entry_price": round(t.entry_price, 6),
                    "exit_price": round(t.exit_price, 6),
                    "stake": round(t.stake, 2),
                    "profit": round(t.profit, 2),
                    "result": t.result,
                    "confidence": round(t.confidence, 3),
                    "reason": t.reason,
                }
                for t in self.trades
            ],
        }


class Backtester:
    """Roda uma estratégia sobre dados históricos, candle a candle."""

    def __init__(
        self,
        strategy_config,
        risk_config=None,
        payout: float = 0.85,
        initial_balance: float = 1000.0,
        expiration_candles: int = 1,
    ):
        self.strategy_cfg = strategy_config
        self.risk_cfg = risk_config
        self.payout = payout
        self.initial_balance = initial_balance
        self.expiration_candles = max(1, expiration_candles)

    def run(self, df: pd.DataFrame, strategy_name: Optional[str] = None,
            symbol: str = "UNKNOWN") -> BacktestResult:
        name = strategy_name or self.strategy_cfg.name
        strategy = get_strategy(name, self.strategy_cfg)

        data = indicators.enrich(df, self.strategy_cfg)
        warmup = strategy.required_candles()

        balance = self.initial_balance
        peak = balance
        result = BacktestResult(
            strategy=name, symbol=symbol, payout=self.payout,
            initial_balance=self.initial_balance, final_balance=balance,
            breakeven_win_rate=100.0 / (1.0 + self.payout),
            candles_tested=max(0, len(data) - warmup),
        )
        result.equity_curve.append(balance)

        stake_pct = getattr(self.risk_cfg, "percent_stake", 1.0) if self.risk_cfg else 1.0
        fixed_stake = getattr(self.risk_cfg, "fixed_stake", 5.0) if self.risk_cfg else 5.0
        sizing = getattr(self.risk_cfg, "sizing_mode", "percent") if self.risk_cfg else "percent"

        busy_until = -1  # índice até o qual há posição aberta
        consecutive_losses = 0
        max_streak = getattr(self.risk_cfg, "max_consecutive_losses", 999) if self.risk_cfg else 999

        # Percorre como se estivesse ao vivo: em i, só existem dados até i.
        for i in range(warmup, len(data) - self.expiration_candles - 1):
            if i <= busy_until:
                continue
            if balance <= 0:
                logger.warning("backtest interrompido: saldo zerado em %s", data["timestamp"].iloc[i])
                break
            if consecutive_losses >= max_streak:
                consecutive_losses = 0  # simula o cooldown liberando após a pausa
                continue

            # A estratégia enxerga apenas até o candle i (que está "em formação")
            window = data.iloc[: i + 1]
            signal = strategy.evaluate(window)
            if not signal.is_actionable:
                continue

            # Entrada no OPEN do próximo candle — sem look-ahead
            entry_idx = i + 1
            exit_idx = entry_idx + self.expiration_candles - 1
            if exit_idx >= len(data):
                break

            entry_price = float(data["open"].iloc[entry_idx])
            exit_price = float(data["close"].iloc[exit_idx])

            stake = fixed_stake if sizing == "fixed" else balance * (stake_pct / 100.0)
            stake = round(min(stake, balance), 2)
            if stake <= 0:
                break

            if exit_price == entry_price:
                profit, res = 0.0, "tie"
            else:
                went_up = exit_price > entry_price
                won = (signal.direction is Direction.CALL) == went_up
                if won:
                    profit, res = stake * self.payout, "won"
                    result.stats.wins += 1
                    result.stats.gross_profit += profit
                    consecutive_losses = 0
                else:
                    profit, res = -stake, "lost"
                    result.stats.losses += 1
                    result.stats.gross_loss += profit
                    consecutive_losses += 1

            if res == "tie":
                result.stats.ties += 1

            balance += profit
            result.stats.total_trades += 1
            result.stats.net_profit += profit
            result.equity_curve.append(balance)

            peak = max(peak, balance)
            dd = peak - balance
            if dd > result.stats.max_drawdown:
                result.stats.max_drawdown = dd
                result.stats.max_drawdown_pct = (dd / peak * 100) if peak else 0.0

            result.trades.append(BacktestTrade(
                entry_time=data["timestamp"].iloc[entry_idx].to_pydatetime(),
                exit_time=data["timestamp"].iloc[exit_idx].to_pydatetime(),
                direction=signal.direction.value,
                entry_price=entry_price, exit_price=exit_price,
                stake=stake, profit=profit, result=res,
                confidence=signal.confidence, reason=signal.reason,
            ))

            busy_until = exit_idx

        result.final_balance = balance
        result.stats.equity_peak = peak
        return result

    def compare(self, df: pd.DataFrame, strategy_names: list[str],
                symbol: str = "UNKNOWN") -> list[dict[str, Any]]:
        """Roda várias estratégias no mesmo dado e ranqueia por lucro líquido."""
        out = []
        for name in strategy_names:
            try:
                out.append(self.run(df, name, symbol).summary())
            except Exception as exc:
                logger.error("falha no backtest de %s: %s", name, exc)
                out.append({"strategy": name, "error": str(exc)})
        return sorted(out, key=lambda r: r.get("net_profit", float("-inf")), reverse=True)
