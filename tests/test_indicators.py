"""Testes dos indicadores — validam as correções de cálculo."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.core import indicators as ind


@pytest.fixture
def series() -> pd.Series:
    rng = np.random.default_rng(7)
    return pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)))


@pytest.fixture
def ohlc() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)))
    open_ = close.shift(1).fillna(100)
    high = pd.concat([open_, close], axis=1).max(axis=1) + abs(rng.normal(0, 0.5, 300))
    low = pd.concat([open_, close], axis=1).min(axis=1) - abs(rng.normal(0, 0.5, 300))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": rng.integers(1, 100, 300).astype(float)})


class TestRSI:
    def test_bounded_0_100(self, series):
        rsi = ind.rsi(series, 14).dropna()
        assert rsi.between(0, 100).all()

    def test_monotonic_rise_gives_100(self):
        rising = pd.Series(np.arange(1, 60, dtype=float))
        assert ind.rsi(rising, 14).iloc[-1] == pytest.approx(100.0)

    def test_monotonic_fall_gives_0(self):
        falling = pd.Series(np.arange(60, 1, -1, dtype=float))
        assert ind.rsi(falling, 14).iloc[-1] == pytest.approx(0.0, abs=1e-6)

    def test_no_division_by_zero_on_flat(self):
        """Bug antigo: série constante gerava NaN por divisão 0/0."""
        flat = pd.Series([100.0] * 60)
        out = ind.rsi(flat, 14)
        assert not out.iloc[-1] != out.iloc[-1]  # não é NaN
        assert out.iloc[-1] == pytest.approx(50.0)

    def test_wilder_differs_from_simple_mean(self, series):
        """Garante que usamos Wilder, não rolling.mean() como na versão antiga."""
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta).clip(lower=0).rolling(14).mean()
        naive = 100 - 100 / (1 + gain / loss)
        assert abs(ind.rsi(series, 14).iloc[-1] - naive.iloc[-1]) > 1e-6

    def test_invalid_period(self, series):
        with pytest.raises(ValueError):
            ind.rsi(series, 1)


class TestMovingAverages:
    def test_sma_matches_manual(self, series):
        assert ind.sma(series, 10).iloc[-1] == pytest.approx(series.tail(10).mean())

    def test_ema_reacts_faster_than_sma(self):
        """Logo após um degrau de preço, a EMA já subiu mais que a SMA."""
        s = pd.Series([10.0] * 50 + [20.0] * 10)
        # 2 candles após o degrau: EMA acumulou mais do novo nível que a SMA
        assert ind.ema(s, 10).iloc[51] > ind.sma(s, 10).iloc[51]
        # ambas convergem para o novo nível quando a janela se completa
        assert ind.sma(s, 10).iloc[-1] == pytest.approx(20.0)

    def test_unknown_type_raises(self, series):
        with pytest.raises(ValueError):
            ind.moving_average(series, 10, "WMA")


class TestBollinger:
    def test_ordering(self, series):
        up, mid, low = ind.bollinger_bands(series, 20, 2.0)
        valid = up.notna()
        assert (up[valid] >= mid[valid]).all()
        assert (mid[valid] >= low[valid]).all()

    def test_percent_b_range(self, series):
        pb = ind.bollinger_percent_b(series, 20, 2.0).dropna()
        assert pb.between(-1.5, 2.5).all()

    def test_flat_series_zero_width(self):
        flat = pd.Series([50.0] * 40)
        up, mid, low = ind.bollinger_bands(flat, 20, 2.0)
        assert up.iloc[-1] == pytest.approx(low.iloc[-1])


class TestATRandADX:
    def test_atr_positive(self, ohlc):
        atr = ind.atr(ohlc["high"], ohlc["low"], ohlc["close"], 14).dropna()
        assert (atr > 0).all()

    def test_true_range_accounts_for_gaps(self):
        high = pd.Series([10.0, 20.0])
        low = pd.Series([9.0, 19.0])
        close = pd.Series([9.5, 19.5])
        tr = ind.true_range(high, low, close)
        assert tr.iloc[1] == pytest.approx(10.5)  # 20 - 9.5, não 20 - 19

    def test_adx_bounded(self, ohlc):
        adx = ind.adx(ohlc["high"], ohlc["low"], ohlc["close"], 14).dropna()
        assert adx.between(0, 100).all()


class TestCrossovers:
    def test_crossover_detects_single_event(self):
        fast = pd.Series([1.0, 2.0, 3.0, 4.0])
        slow = pd.Series([3.0, 3.0, 2.5, 2.0])
        assert ind.crossover(fast, slow).tolist() == [False, False, True, False]

    def test_crossunder(self):
        fast = pd.Series([4.0, 3.0, 2.0])
        slow = pd.Series([1.0, 2.5, 3.0])
        assert ind.crossunder(fast, slow).tolist() == [False, False, True]


class TestEnrich:
    def test_adds_all_columns_without_mutating(self, ohlc):
        from trading_bot.core.config import StrategyConfig
        before = ohlc.columns.tolist()
        out = ind.enrich(ohlc, StrategyConfig())
        for col in ("rsi", "ma_fast", "ma_slow", "bb_upper", "macd", "atr", "adx", "atr_pct"):
            assert col in out.columns
        assert ohlc.columns.tolist() == before  # original intacto
