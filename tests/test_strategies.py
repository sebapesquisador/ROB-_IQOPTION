"""Testes das estratégias: contrato, ausência de look-ahead e filtros."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.core import indicators as ind
from trading_bot.core.config import StrategyConfig
from trading_bot.core.models import Direction, Signal
from trading_bot.core.strategies import available_strategies, get_strategy
from trading_bot.core.strategies.base import Strategy, _REGISTRY

ALL = [s["name"] for s in available_strategies()]


def make_df(n: int = 400, seed: int = 3, trend: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, 0.002, n)
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.001, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.001, n)))
    ts = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame({"timestamp": ts, "open": open_, "high": high, "low": low,
                       "close": close, "volume": rng.integers(1, 100, n).astype(float)})
    return ind.enrich(df, StrategyConfig())


@pytest.fixture
def cfg() -> StrategyConfig:
    return StrategyConfig(min_confidence=0.0, require_trend_alignment=False)


class TestRegistry:
    def test_has_expected_strategies(self):
        assert set(ALL) >= {
            "rsi_reversal", "trend_pullback", "bollinger_reversion",
            "macd_momentum", "confluence",
        }

    def test_unknown_raises(self, cfg):
        with pytest.raises(KeyError):
            get_strategy("nao_existe", cfg)

    def test_all_have_description(self):
        for s in available_strategies():
            assert s["description"], f"{s['name']} sem docstring"


@pytest.mark.parametrize("name", ALL)
class TestContract:
    def test_returns_signal(self, name, cfg):
        sig = get_strategy(name, cfg).evaluate(make_df())
        assert isinstance(sig, Signal)
        assert 0.0 <= sig.confidence <= 1.0
        assert sig.direction in (Direction.CALL, Direction.PUT, Direction.NONE)

    def test_insufficient_data_is_safe(self, name, cfg):
        sig = get_strategy(name, cfg).evaluate(make_df(n=20))
        assert sig.direction is Direction.NONE

    def test_none_dataframe_is_safe(self, name, cfg):
        assert get_strategy(name, cfg).evaluate(None).direction is Direction.NONE

    def test_does_not_mutate_input(self, name, cfg):
        df = make_df()
        before = df.copy(deep=True)
        get_strategy(name, cfg).evaluate(df)
        pd.testing.assert_frame_equal(df, before)

    def test_no_lookahead(self, name, cfg):
        """
        O sinal não pode mudar quando o candle EM FORMAÇÃO muda.
        Se mudar, a estratégia está lendo o futuro e o backtest é inválido.
        """
        df = make_df()
        strat = get_strategy(name, cfg)
        sig_a = strat.evaluate(df)

        tampered = df.copy()
        last = len(tampered) - 1
        tampered.loc[last, "close"] *= 1.05   # altera só o candle em formação
        tampered.loc[last, "high"] *= 1.06
        sig_b = strat.evaluate(tampered)

        assert sig_a.direction is sig_b.direction, (
            f"{name} muda de sinal quando o candle em formação muda — look-ahead bias"
        )

    def test_deterministic(self, name, cfg):
        df = make_df()
        strat = get_strategy(name, cfg)
        assert strat.evaluate(df).direction is strat.evaluate(df).direction

    def test_handles_nan_tail(self, name, cfg):
        df = make_df()
        df.loc[len(df) - 2, "close"] = np.nan
        assert get_strategy(name, cfg).evaluate(df).direction is Direction.NONE


class TestFilters:
    def test_min_confidence_blocks_weak_signals(self):
        df = make_df()
        loose = get_strategy("confluence", StrategyConfig(min_confidence=0.0))
        strict = get_strategy("confluence", StrategyConfig(min_confidence=0.99))
        if loose.evaluate(df).is_actionable:
            assert not strict.evaluate(df).is_actionable

    def test_volatility_filter_blocks(self):
        df = make_df()
        cfg = StrategyConfig(min_confidence=0.0, min_atr_pct=50.0)  # impossível
        for name in ALL:
            assert not get_strategy(name, cfg).evaluate(df).is_actionable

    def test_signal_carries_indicators_and_reason(self, ):
        df = make_df()
        for name in ALL:
            sig = get_strategy(name, StrategyConfig(min_confidence=0.0)).evaluate(df)
            assert sig.reason, f"{name} sem justificativa"
            if sig.is_actionable:
                assert sig.strategy == name


class TestHelpers:
    def test_last_closed_is_index_minus_2(self, cfg):
        df = make_df(n=100)
        strat = get_strategy("rsi_reversal", cfg)
        assert strat.last_closed(df)["close"] == df["close"].iloc[-2]
        assert strat.previous_closed(df)["close"] == df["close"].iloc[-3]

    def test_trend_direction(self, cfg):
        strat = get_strategy("rsi_reversal", cfg)
        row = pd.Series({"close": 110.0, "ma_slow": 100.0})
        assert strat.trend_direction(row) is Direction.CALL
        row = pd.Series({"close": 90.0, "ma_slow": 100.0})
        assert strat.trend_direction(row) is Direction.PUT
