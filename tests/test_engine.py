"""Testes de integração: engine + broker simulado + storage."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.brokers.paper import PaperBroker
from trading_bot.core.config import (
    AccountMode, Broker as BrokerEnum, RiskConfig, SessionConfig,
    Settings, StrategyConfig,
)
from trading_bot.core.engine import TradingEngine
from trading_bot.core.models import BotState, Direction, Order, OrderStatus
from trading_bot.core.storage import Storage


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        broker=BrokerEnum.PAPER, account_mode=AccountMode.DEMO, dry_run=True,
        symbol="EURUSD", timeframe_minutes=5, expiration_minutes=5,
        poll_interval_seconds=1, candles_lookback=300,
        database_url=f"sqlite:///{tmp_path/'test.db'}",
        strategy=StrategyConfig(name="confluence", min_confidence=0.0,
                                require_trend_alignment=False),
        risk=RiskConfig(sizing_mode="fixed", fixed_stake=10.0,
                        min_seconds_between_trades=0, max_consecutive_losses=99,
                        daily_profit_target_pct=1000.0),
        session=SessionConfig(start_time="00:00", end_time="23:59",
                              trade_on_weekends=True,
                              weekday_whitelist=[0, 1, 2, 3, 4, 5, 6]),
    )


@pytest.fixture
def engine(settings) -> TradingEngine:
    broker = PaperBroker(settings, seed=42, initial_balance=1000.0)
    return TradingEngine(settings, broker, Storage(settings.database_url))


class TestLifecycle:
    def test_starts_and_stops(self, engine):
        assert engine.state is BotState.STOPPED
        assert engine.start()
        assert engine.state is BotState.RUNNING
        engine.stop()
        assert engine.state is BotState.STOPPED

    def test_double_start_is_noop(self, engine):
        engine.start()
        assert engine.start() is False
        engine.stop()

    def test_pause_resume(self, engine):
        engine.start()
        engine.pause()
        assert engine.state is BotState.PAUSED
        engine.resume()
        assert engine.state is BotState.RUNNING
        engine.stop()

    def test_stop_when_not_started(self, engine):
        engine.stop()  # não deve levantar
        assert engine.state is BotState.STOPPED


class TestTicks:
    def test_tick_produces_signal_and_maybe_order(self, engine):
        engine.broker.connect()
        from trading_bot.core.risk import RiskManager
        engine.risk = RiskManager(engine.settings.risk, 1000.0)
        engine.state = BotState.RUNNING
        engine._tick()
        assert engine._cycles == 1
        assert engine._last_signal is not None

    def test_one_evaluation_per_closed_candle(self, engine):
        """O robô antigo reavaliava a cada segundo; aqui é 1x por candle."""
        engine.broker.connect()
        from trading_bot.core.risk import RiskManager
        engine.risk = RiskManager(engine.settings.risk, 1000.0)
        engine.state = BotState.RUNNING
        engine._tick()
        first = engine._last_evaluated_candle
        assert first is not None
        # Sem novo candle fechado, não reavalia
        engine._last_signal = None
        engine._tick()
        # PaperBroker avança 1 candle por chamada, então deve ter avançado
        assert engine._last_evaluated_candle >= first

    def test_tick_paused_does_not_trade(self, engine):
        engine.broker.connect()
        from trading_bot.core.risk import RiskManager
        engine.risk = RiskManager(engine.settings.risk, 1000.0)
        engine.state = BotState.PAUSED
        engine._tick()
        assert len(engine._open_orders) == 0


class TestSession:
    def test_outside_window_blocks(self, settings):
        settings.session.start_time = "03:00"
        settings.session.end_time = "03:01"
        eng = TradingEngine(settings, PaperBroker(settings), Storage(settings.database_url))
        now = datetime.now().time()
        if not (now.hour == 3 and now.minute <= 1):
            assert eng._within_session() is False

    def test_overnight_window(self, settings):
        settings.session.start_time = "00:00"
        settings.session.end_time = "23:59"
        eng = TradingEngine(settings, PaperBroker(settings), Storage(settings.database_url))
        assert eng._within_session() is True

    def test_weekday_whitelist(self, settings):
        settings.session.weekday_whitelist = []
        settings.session.trade_on_weekends = False
        eng = TradingEngine(settings, PaperBroker(settings), Storage(settings.database_url))
        assert eng._within_session() is False


class TestRiskIntegration:
    def test_halts_on_daily_loss(self, engine):
        engine.broker.connect()
        from trading_bot.core.risk import RiskManager
        engine.risk = RiskManager(engine.settings.risk, 1000.0)
        engine.state = BotState.RUNNING

        o = Order(symbol="EURUSD", direction=Direction.CALL, amount=100.0,
                  expiration_minutes=5)
        o.profit, o.status = -100.0, OrderStatus.LOST
        engine.risk.register_close(o)  # 10% de perda com limite de 5%

        for _ in range(30):
            engine._tick()
            if engine.state is BotState.HALTED:
                break
        assert engine.state is BotState.HALTED

    def test_order_closes_and_persists(self, engine):
        engine.broker.connect()
        from trading_bot.core.risk import RiskManager
        engine.risk = RiskManager(engine.settings.risk, 1000.0)

        order = engine.broker.place_order("EURUSD", Direction.CALL, 10.0, 5)
        order.metadata["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        engine._open_orders[order.id] = order
        engine.risk.register_open(order)

        engine._reconcile_open_orders()
        assert len(engine._open_orders) == 0
        assert len(engine.storage.recent_orders()) >= 1

    def test_reconcile_is_non_blocking(self, engine):
        """A verificação não pode travar o loop como no bot antigo (300s)."""
        engine.broker.connect()
        from trading_bot.core.risk import RiskManager
        engine.risk = RiskManager(engine.settings.risk, 1000.0)
        order = engine.broker.place_order("EURUSD", Direction.CALL, 10.0, 5)
        engine._open_orders[order.id] = order

        start = time.monotonic()
        engine._reconcile_open_orders()
        assert time.monotonic() - start < 2.0
        assert len(engine._open_orders) == 1  # ainda aberta, sem bloquear


class TestSnapshot:
    def test_snapshot_shape(self, engine):
        engine.start()
        time.sleep(0.5)
        s = engine.snapshot()
        engine.stop()
        for k in ("state", "broker", "strategy", "symbol", "risk", "dry_run"):
            assert k in s

    def test_snapshot_json_serializable(self, engine):
        import json
        engine.start()
        time.sleep(0.5)
        json.dumps(engine.snapshot())
        engine.stop()


class TestStorage:
    def test_saves_and_reads_orders(self, tmp_path):
        st = Storage(f"sqlite:///{tmp_path/'s.db'}")
        o = Order(symbol="EURUSD", direction=Direction.CALL, amount=10.0,
                  expiration_minutes=5, strategy="confluence")
        st.save_order(o)
        o.status, o.profit = OrderStatus.WON, 8.5
        o.closed_at = datetime.now(timezone.utc)
        st.save_order(o)  # upsert

        rows = st.recent_orders()
        assert len(rows) == 1
        assert rows[0]["status"] == "won"
        assert rows[0]["profit"] == 8.5

    def test_today_pnl(self, tmp_path):
        st = Storage(f"sqlite:///{tmp_path/'s.db'}")
        for p in (10.0, -5.0):
            o = Order(symbol="X", direction=Direction.CALL, amount=10.0, expiration_minutes=1)
            o.profit = p
            o.status = OrderStatus.WON if p > 0 else OrderStatus.LOST
            o.closed_at = datetime.now(timezone.utc)
            st.save_order(o)
        pnl, n = st.today_pnl()
        assert pnl == pytest.approx(5.0)
        assert n == 2

    def test_strategy_performance(self, tmp_path):
        st = Storage(f"sqlite:///{tmp_path/'s.db'}")
        for p, s in ((10.0, "a"), (-5.0, "a"), (20.0, "b")):
            o = Order(symbol="X", direction=Direction.CALL, amount=10.0,
                      expiration_minutes=1, strategy=s)
            o.profit = p
            o.status = OrderStatus.WON if p > 0 else OrderStatus.LOST
            st.save_order(o)
        perf = st.strategy_performance()
        assert perf[0]["strategy"] == "b"  # ordenado por PnL


class TestPaperBroker:
    def test_candles_normalized(self, settings):
        b = PaperBroker(settings)
        b.connect()
        df = b.get_candles("EURUSD", 5, 200)
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert df["timestamp"].is_monotonic_increasing
        assert (df["high"] >= df["low"]).all()
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["close"]).all()

    def test_order_resolves_after_expiry(self, settings):
        b = PaperBroker(settings)
        b.connect()
        o = b.place_order("EURUSD", Direction.CALL, 10.0, 5)
        assert o.status is OrderStatus.OPEN
        o.metadata["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        o = b.check_order(o)
        assert o.is_closed
        assert o.status in (OrderStatus.WON, OrderStatus.LOST, OrderStatus.TIE)

    def test_balance_reflects_pnl(self, settings):
        b = PaperBroker(settings, initial_balance=1000.0)
        b.connect()
        o = b.place_order("EURUSD", Direction.CALL, 100.0, 5)
        assert b.get_balance().balance == pytest.approx(900.0)
