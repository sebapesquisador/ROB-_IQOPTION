"""
Testes do RiskManager.

Estes são os testes mais importantes do projeto: cada um representa um
cenário em que o robô antigo teria continuado operando até zerar a conta.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.core.config import RiskConfig
from trading_bot.core.models import Direction, Order, OrderStatus
from trading_bot.core.risk import RejectReason, RiskManager


def make_order(profit: float, amount: float = 10.0) -> Order:
    o = Order(symbol="EURUSD", direction=Direction.CALL, amount=amount, expiration_minutes=5)
    o.profit = profit
    o.status = OrderStatus.WON if profit > 0 else (
        OrderStatus.LOST if profit < 0 else OrderStatus.TIE
    )
    o.closed_at = datetime.now(timezone.utc)
    return o


@pytest.fixture
def cfg() -> RiskConfig:
    return RiskConfig(
        sizing_mode="percent", percent_stake=2.0,
        max_daily_loss_pct=10.0, max_total_drawdown_pct=20.0,
        max_consecutive_losses=3, cooldown_after_loss_streak_min=30,
        daily_profit_target_pct=10.0, max_trades_per_day=20,
        max_concurrent_positions=1, min_seconds_between_trades=0,
    )


@pytest.fixture
def rm(cfg) -> RiskManager:
    return RiskManager(cfg, starting_balance=1000.0)


class TestSizing:
    def test_percent_sizing(self, rm):
        assert rm.calculate_stake() == pytest.approx(20.0)  # 2% de 1000

    def test_fixed_sizing(self, cfg):
        cfg.sizing_mode = "fixed"
        cfg.fixed_stake = 7.5
        assert RiskManager(cfg, 1000.0).calculate_stake() == pytest.approx(7.5)

    def test_stake_shrinks_with_balance(self, rm):
        rm.register_close(make_order(-500.0))
        # saldo caiu para 500 => 2% = 10
        assert rm.calculate_stake() == pytest.approx(10.0)

    def test_stake_capped_by_remaining_loss_budget(self, cfg):
        cfg.percent_stake = 5.0
        rm = RiskManager(cfg, 1000.0)
        rm.register_close(make_order(-95.0))  # restam 5 do orçamento de 100
        assert rm.calculate_stake() <= 5.0

    def test_never_exceeds_balance(self, cfg):
        cfg.sizing_mode = "fixed"
        cfg.fixed_stake = 10_000.0
        rm = RiskManager(cfg, 50.0)
        assert rm.calculate_stake() <= 50.0


class TestDailyLossLimit:
    def test_blocks_at_limit(self, rm):
        rm.register_close(make_order(-100.0))  # 10% de 1000
        d = rm.approve()
        assert not d.approved
        assert d.reason is RejectReason.DAILY_LOSS_LIMIT

    def test_allows_below_limit(self, rm):
        rm.register_close(make_order(-50.0))
        assert rm.approve().approved

    def test_budget_decreases(self, rm):
        assert rm.remaining_daily_loss_budget() == pytest.approx(100.0)
        rm.register_close(make_order(-30.0))
        assert rm.remaining_daily_loss_budget() == pytest.approx(70.0)

    def test_profit_does_not_inflate_budget(self, rm):
        rm.register_close(make_order(50.0))
        assert rm.remaining_daily_loss_budget() == pytest.approx(100.0)


class TestDrawdown:
    def test_blocks_beyond_max_drawdown(self, rm):
        rm.register_close(make_order(500.0))   # pico 1500
        rm.cfg.max_daily_loss_pct = 100.0      # isola o teste de drawdown
        rm.register_close(make_order(-320.0))  # 1180 => dd ~21%
        d = rm.approve()
        assert not d.approved
        assert d.reason is RejectReason.DRAWDOWN_LIMIT

    def test_tracks_peak_and_max_dd(self, rm):
        rm.register_close(make_order(200.0))
        rm.register_close(make_order(-100.0))
        assert rm.equity_peak == pytest.approx(1200.0)
        assert rm.stats.max_drawdown == pytest.approx(100.0)


class TestLossStreak:
    def test_cooldown_after_streak(self, rm):
        for _ in range(3):
            rm.register_close(make_order(-10.0))
        d = rm.approve()
        assert not d.approved
        assert d.reason is RejectReason.LOSS_STREAK

    def test_win_resets_streak(self, rm):
        rm.register_close(make_order(-10.0))
        rm.register_close(make_order(-10.0))
        rm.register_close(make_order(10.0))
        rm.register_close(make_order(-10.0))
        assert rm.approve().approved

    def test_cooldown_expires(self, rm):
        for _ in range(3):
            rm.register_close(make_order(-10.0))
        rm._book.halted_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert rm.approve().approved


class TestTargetsAndLimits:
    def test_stops_at_daily_target(self, rm):
        rm.register_close(make_order(100.0))  # meta 10%
        d = rm.approve()
        assert not d.approved
        assert d.reason is RejectReason.DAILY_TARGET_REACHED

    def test_max_trades_per_day(self, cfg):
        cfg.max_trades_per_day = 2
        cfg.daily_profit_target_pct = 1000.0
        rm = RiskManager(cfg, 1000.0)
        rm.register_close(make_order(1.0))
        rm.register_close(make_order(1.0))
        assert rm.approve().reason is RejectReason.MAX_TRADES

    def test_max_concurrent_positions(self, rm):
        rm.register_open(make_order(0.0))
        assert rm.approve().reason is RejectReason.MAX_CONCURRENT

    def test_min_interval_between_trades(self, cfg):
        cfg.min_seconds_between_trades = 60
        cfg.max_concurrent_positions = 5
        rm = RiskManager(cfg, 1000.0)
        rm.register_open(make_order(0.0))
        assert rm.approve().reason is RejectReason.TOO_SOON

    def test_rejects_stake_below_broker_minimum(self, cfg):
        cfg.percent_stake = 0.1
        rm = RiskManager(cfg, 100.0)  # stake = 0.10
        assert rm.approve(min_stake=1.0).reason is RejectReason.INVALID_STAKE


class TestMartingale:
    def test_disabled_by_default(self):
        assert RiskConfig().martingale_enabled is False

    def test_escalates_then_caps(self, cfg):
        cfg.martingale_enabled = True
        cfg.martingale_multiplier = 2.0
        cfg.martingale_max_steps = 2
        cfg.max_daily_loss_pct = 90.0
        rm = RiskManager(cfg, 1000.0)
        base = rm.calculate_stake()
        rm.register_close(make_order(-base))
        assert rm.calculate_stake() > base
        rm.register_close(make_order(-base))
        step2 = rm._martingale_step
        rm.register_close(make_order(-base))
        assert rm._martingale_step == 0  # resetou ao atingir o teto

    def test_win_resets_martingale(self, cfg):
        cfg.martingale_enabled = True
        rm = RiskManager(cfg, 1000.0)
        rm.register_close(make_order(-20.0))
        assert rm._martingale_step == 1
        rm.register_close(make_order(20.0))
        assert rm._martingale_step == 0


class TestStats:
    def test_win_rate_and_profit_factor(self, rm):
        rm.cfg.daily_profit_target_pct = 1000.0
        rm.register_close(make_order(8.0))
        rm.register_close(make_order(8.0))
        rm.register_close(make_order(-10.0))
        assert rm.stats.win_rate == pytest.approx(66.67, abs=0.01)
        assert rm.stats.profit_factor == pytest.approx(1.6)

    def test_expectancy_negative_when_losing(self, rm):
        rm.register_close(make_order(-10.0))
        rm.register_close(make_order(8.0))
        assert rm.stats.expectancy < 0

    def test_streak_tracking(self, rm):
        rm.cfg.daily_profit_target_pct = 1000.0
        rm.cfg.max_consecutive_losses = 99
        for p in (10.0, 10.0, 10.0, -10.0, -10.0):
            rm.register_close(make_order(p))
        assert rm.stats.max_win_streak == 3
        assert rm.stats.max_loss_streak == 2

    def test_snapshot_serializable(self, rm):
        snap = rm.snapshot()
        assert {"balance", "daily_pnl", "next_stake", "stats"} <= snap.keys()


class TestDayRollover:
    def test_new_day_resets_book(self, rm):
        rm.register_close(make_order(-80.0))
        rm._book.day = rm._book.day.replace(day=max(1, rm._book.day.day - 1))
        rm._roll_day_if_needed()
        assert rm._book.realized_pnl == 0.0
        assert rm._book.trades == 0
        assert rm.approve().approved
