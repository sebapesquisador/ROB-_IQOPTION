"""
Gestão de risco.

Esta é a camada que faltava por completo no projeto original: não havia
stop diário, nem limite de drawdown, nem controle de sequência de perdas,
nem dimensionamento de posição relativo ao saldo. O robô simplesmente
operava até a conta acabar.

Regra de ouro: NENHUMA ordem é enviada sem passar por `RiskManager.approve()`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from .models import Order, OrderStatus, PerformanceStats

logger = logging.getLogger(__name__)


class RejectReason(str, Enum):
    OK = "ok"
    DAILY_LOSS_LIMIT = "limite de perda diária atingido"
    DRAWDOWN_LIMIT = "drawdown máximo atingido"
    LOSS_STREAK = "sequência de derrotas — em cooldown"
    DAILY_TARGET_REACHED = "meta diária atingida"
    MAX_TRADES = "número máximo de trades do dia atingido"
    MAX_CONCURRENT = "número máximo de posições simultâneas atingido"
    TOO_SOON = "intervalo mínimo entre trades não cumprido"
    INSUFFICIENT_BALANCE = "saldo insuficiente"
    INVALID_STAKE = "valor de entrada inválido"


@dataclass(slots=True)
class RiskDecision:
    """Resultado da avaliação de risco para uma entrada."""

    approved: bool
    stake: float = 0.0
    reason: RejectReason = RejectReason.OK
    detail: str = ""

    def __bool__(self) -> bool:
        return self.approved


@dataclass(slots=True)
class DayBook:
    """Contabilidade do dia corrente. Reseta automaticamente na virada."""

    day: date
    starting_balance: float
    realized_pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    halted_until: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None


class RiskManager:
    """Avalia cada entrada e mantém a contabilidade de risco."""

    def __init__(self, config, starting_balance: float):
        self.cfg = config
        self.starting_balance = starting_balance
        self.current_balance = starting_balance
        self.equity_peak = starting_balance
        self.open_positions = 0
        self.stats = PerformanceStats(equity_peak=starting_balance)
        self._book = DayBook(day=self._today(), starting_balance=starting_balance)
        self._martingale_step = 0

    # ------------------------------------------------------------------ #
    # Utilidades internas
    # ------------------------------------------------------------------ #

    @staticmethod
    def _today() -> date:
        return datetime.now(timezone.utc).date()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _roll_day_if_needed(self) -> None:
        today = self._today()
        if self._book.day != today:
            logger.info(
                "Virada de dia: %s encerrado com PnL %.2f em %d trades",
                self._book.day, self._book.realized_pnl, self._book.trades,
            )
            self._book = DayBook(day=today, starting_balance=self.current_balance)
            self._martingale_step = 0

    # ------------------------------------------------------------------ #
    # Dimensionamento de posição
    # ------------------------------------------------------------------ #

    def calculate_stake(self) -> float:
        """Calcula o valor da próxima entrada respeitando o modo configurado."""
        if self.cfg.sizing_mode == "fixed":
            base = self.cfg.fixed_stake
        else:
            base = self.current_balance * (self.cfg.percent_stake / 100.0)

        # Martingale (desligado por padrão — é matematicamente ruinoso a longo prazo)
        if self.cfg.martingale_enabled and self._martingale_step > 0:
            base *= self.cfg.martingale_multiplier ** self._martingale_step

        # Nunca arrisca mais que o restante permitido da perda diária
        remaining = self.remaining_daily_loss_budget()
        if remaining > 0:
            base = min(base, remaining)

        # Nunca arrisca mais que o saldo disponível
        base = min(base, self.current_balance)
        return round(max(base, 0.0), 2)

    def remaining_daily_loss_budget(self) -> float:
        """Quanto ainda pode ser perdido hoje antes de bater o stop diário."""
        max_loss = self._book.starting_balance * (self.cfg.max_daily_loss_pct / 100.0)
        already_lost = max(0.0, -self._book.realized_pnl)
        return max(0.0, max_loss - already_lost)

    # ------------------------------------------------------------------ #
    # Avaliação principal
    # ------------------------------------------------------------------ #

    def approve(self, min_stake: float = 1.0) -> RiskDecision:
        """
        Decide se uma nova entrada pode ser aberta e com que valor.
        Chame este método imediatamente antes de enviar qualquer ordem.
        """
        self._roll_day_if_needed()
        now = self._now()

        # 1. Cooldown por sequência de derrotas
        if self._book.halted_until and now < self._book.halted_until:
            restante = int((self._book.halted_until - now).total_seconds() / 60)
            return RiskDecision(
                False, reason=RejectReason.LOSS_STREAK,
                detail=f"cooldown ativo por mais {restante} min",
            )

        # 2. Stop de perda diária
        max_daily_loss = self._book.starting_balance * (self.cfg.max_daily_loss_pct / 100.0)
        if -self._book.realized_pnl >= max_daily_loss:
            return RiskDecision(
                False, reason=RejectReason.DAILY_LOSS_LIMIT,
                detail=f"perda de {-self._book.realized_pnl:.2f} >= limite {max_daily_loss:.2f}",
            )

        # 3. Drawdown máximo sobre o pico de equity
        if self.equity_peak > 0:
            dd_pct = (self.equity_peak - self.current_balance) / self.equity_peak * 100
            if dd_pct >= self.cfg.max_total_drawdown_pct:
                return RiskDecision(
                    False, reason=RejectReason.DRAWDOWN_LIMIT,
                    detail=f"drawdown {dd_pct:.2f}% >= limite {self.cfg.max_total_drawdown_pct}%",
                )

        # 4. Meta diária atingida — parar de operar é parte da estratégia
        target = self._book.starting_balance * (self.cfg.daily_profit_target_pct / 100.0)
        if self._book.realized_pnl >= target > 0:
            return RiskDecision(
                False, reason=RejectReason.DAILY_TARGET_REACHED,
                detail=f"lucro {self._book.realized_pnl:.2f} >= meta {target:.2f}",
            )

        # 5. Teto de trades por dia
        if self._book.trades >= self.cfg.max_trades_per_day:
            return RiskDecision(
                False, reason=RejectReason.MAX_TRADES,
                detail=f"{self._book.trades}/{self.cfg.max_trades_per_day}",
            )

        # 6. Posições simultâneas
        if self.open_positions >= self.cfg.max_concurrent_positions:
            return RiskDecision(
                False, reason=RejectReason.MAX_CONCURRENT,
                detail=f"{self.open_positions}/{self.cfg.max_concurrent_positions}",
            )

        # 7. Intervalo mínimo entre entradas (evita overtrading em ruído)
        if self._book.last_trade_at:
            elapsed = (now - self._book.last_trade_at).total_seconds()
            if elapsed < self.cfg.min_seconds_between_trades:
                return RiskDecision(
                    False, reason=RejectReason.TOO_SOON,
                    detail=f"aguardando {self.cfg.min_seconds_between_trades - int(elapsed)}s",
                )

        # 8. Dimensionamento
        stake = self.calculate_stake()
        if stake < min_stake:
            return RiskDecision(
                False, reason=RejectReason.INVALID_STAKE,
                detail=f"stake calculado {stake:.2f} < mínimo {min_stake:.2f}",
            )
        if stake > self.current_balance:
            return RiskDecision(
                False, reason=RejectReason.INSUFFICIENT_BALANCE,
                detail=f"stake {stake:.2f} > saldo {self.current_balance:.2f}",
            )

        return RiskDecision(True, stake=stake)

    # ------------------------------------------------------------------ #
    # Registro de eventos
    # ------------------------------------------------------------------ #

    def register_open(self, order: Order) -> None:
        self._roll_day_if_needed()
        self.open_positions += 1
        self._book.last_trade_at = self._now()

    def register_close(self, order: Order) -> None:
        """Atualiza toda a contabilidade após o fechamento de uma ordem."""
        self._roll_day_if_needed()
        self.open_positions = max(0, self.open_positions - 1)

        profit = order.profit
        self.current_balance += profit
        self._book.realized_pnl += profit
        self._book.trades += 1

        # Estatísticas agregadas
        self.stats.total_trades += 1
        self.stats.net_profit += profit

        if order.status is OrderStatus.WON:
            self._book.wins += 1
            self._book.consecutive_losses = 0
            self._martingale_step = 0
            self.stats.wins += 1
            self.stats.gross_profit += profit
            self.stats.current_streak = max(1, self.stats.current_streak + 1)
            self.stats.max_win_streak = max(self.stats.max_win_streak, self.stats.current_streak)

        elif order.status is OrderStatus.LOST:
            self._book.losses += 1
            self._book.consecutive_losses += 1
            self.stats.losses += 1
            self.stats.gross_loss += profit
            self.stats.current_streak = min(-1, self.stats.current_streak - 1)
            self.stats.max_loss_streak = max(self.stats.max_loss_streak, -self.stats.current_streak)

            if self.cfg.martingale_enabled and self._martingale_step < self.cfg.martingale_max_steps:
                self._martingale_step += 1
            else:
                self._martingale_step = 0

            # Aciona cooldown ao atingir a sequência limite
            if self._book.consecutive_losses >= self.cfg.max_consecutive_losses:
                self._book.halted_until = self._now() + timedelta(
                    minutes=self.cfg.cooldown_after_loss_streak_min
                )
                logger.warning(
                    "RISCO: %d derrotas seguidas. Robô pausado até %s",
                    self._book.consecutive_losses, self._book.halted_until.isoformat(),
                )
                self._book.consecutive_losses = 0
        else:
            self.stats.ties += 1

        # Curva de equity e drawdown
        self.equity_peak = max(self.equity_peak, self.current_balance)
        self.stats.equity_peak = self.equity_peak
        dd = self.equity_peak - self.current_balance
        if dd > self.stats.max_drawdown:
            self.stats.max_drawdown = dd
            self.stats.max_drawdown_pct = (dd / self.equity_peak * 100) if self.equity_peak else 0.0

    def sync_balance(self, balance: float) -> None:
        """Sincroniza com o saldo real da corretora (fonte de verdade)."""
        self.current_balance = balance
        self.equity_peak = max(self.equity_peak, balance)

    # ------------------------------------------------------------------ #
    # Introspecção
    # ------------------------------------------------------------------ #

    def snapshot(self) -> dict:
        self._roll_day_if_needed()
        max_daily_loss = self._book.starting_balance * (self.cfg.max_daily_loss_pct / 100.0)
        target = self._book.starting_balance * (self.cfg.daily_profit_target_pct / 100.0)
        dd_pct = (
            (self.equity_peak - self.current_balance) / self.equity_peak * 100
            if self.equity_peak else 0.0
        )
        return {
            "balance": round(self.current_balance, 2),
            "equity_peak": round(self.equity_peak, 2),
            "drawdown_pct": round(dd_pct, 2),
            "open_positions": self.open_positions,
            "day": self._book.day.isoformat(),
            "daily_pnl": round(self._book.realized_pnl, 2),
            "daily_trades": self._book.trades,
            "daily_wins": self._book.wins,
            "daily_losses": self._book.losses,
            "daily_loss_limit": round(max_daily_loss, 2),
            "daily_loss_used_pct": round(
                (max(0.0, -self._book.realized_pnl) / max_daily_loss * 100) if max_daily_loss else 0.0, 1
            ),
            "daily_target": round(target, 2),
            "consecutive_losses": self._book.consecutive_losses,
            "halted_until": self._book.halted_until.isoformat() if self._book.halted_until else None,
            "next_stake": self.calculate_stake(),
            "martingale_step": self._martingale_step,
            "stats": self.stats.to_dict(),
        }
