"""Testes do backtester, incluindo a matemática do payout."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtest import Backtester
from trading_bot.core.config import RiskConfig, StrategyConfig
from trading_bot.core.strategies import available_strategies

ALL = [s["name"] for s in available_strategies()]


def make_df(n: int = 800, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.001, n)))
    low = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.001, n)))
    ts = pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "open": open_, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 100, n).astype(float)})


@pytest.fixture
def bt() -> Backtester:
    return Backtester(
        strategy_config=StrategyConfig(min_confidence=0.0, require_trend_alignment=False),
        risk_config=RiskConfig(sizing_mode="fixed", fixed_stake=10.0, max_consecutive_losses=999),
        payout=0.85, initial_balance=1000.0,
    )


class TestPayoutMath:
    @pytest.mark.parametrize("payout,expected", [
        (0.85, 54.05), (0.80, 55.56), (0.90, 52.63), (1.00, 50.0),
    ])
    def test_breakeven_win_rate(self, payout, expected):
        """Com payout de 85%, acertar 54,05% apenas empata."""
        b = Backtester(StrategyConfig(), payout=payout)
        r = b.run(make_df(300), "rsi_reversal")
        assert r.breakeven_win_rate == pytest.approx(expected, abs=0.01)

    def test_fifty_percent_accuracy_loses_money(self, bt):
        """Prova numérica: 50% de acerto com payout 85% destrói a banca."""
        stake, n = 10.0, 100
        final = 1000.0 + (n / 2) * stake * 0.85 - (n / 2) * stake
        assert final < 1000.0
        assert final == pytest.approx(925.0)


class TestExecution:
    @pytest.mark.parametrize("name", ALL)
    def test_runs_without_error(self, bt, name):
        r = bt.run(make_df(), name)
        assert r.strategy == name
        assert r.candles_tested > 0
        assert len(r.equity_curve) == r.stats.total_trades + 1

    def test_accounting_is_consistent(self, bt):
        r = bt.run(make_df(), "confluence")
        assert r.stats.total_trades == r.stats.wins + r.stats.losses + r.stats.ties
        assert r.final_balance == pytest.approx(
            r.initial_balance + r.stats.net_profit, abs=0.01
        )

    def test_no_overlapping_trades(self, bt):
        """Com 1 posição por vez, nenhum trade pode começar antes do anterior fechar."""
        r = bt.run(make_df(), "confluence")
        for a, b in zip(r.trades, r.trades[1:]):
            assert b.entry_time > a.exit_time

    def test_entry_uses_next_candle_open(self, bt):
        """Garante ausência de look-ahead: entrada é no open seguinte ao sinal."""
        df = make_df()
        r = bt.run(df, "confluence")
        if not r.trades:
            pytest.skip("sem trades nesta amostra")
        t = r.trades[0]
        row = df[df["timestamp"] == pd.Timestamp(t.entry_time)]
        assert t.entry_price == pytest.approx(float(row["open"].iloc[0]))

    def test_stops_when_balance_zero(self):
        b = Backtester(
            StrategyConfig(min_confidence=0.0),
            RiskConfig(sizing_mode="fixed", fixed_stake=10_000.0, max_consecutive_losses=999),
            payout=0.85, initial_balance=100.0,
        )
        r = b.run(make_df(), "confluence")
        assert r.final_balance >= 0

    def test_percent_sizing_compounds(self):
        b = Backtester(
            StrategyConfig(min_confidence=0.0),
            RiskConfig(sizing_mode="percent", percent_stake=2.0, max_consecutive_losses=999),
            payout=0.85, initial_balance=1000.0,
        )
        r = b.run(make_df(), "confluence")
        if len(r.trades) > 1:
            assert r.trades[0].stake != r.trades[-1].stake or r.stats.net_profit == 0


class TestResult:
    def test_summary_has_key_metrics(self, bt):
        s = bt.run(make_df(), "confluence").summary()
        for k in ("win_rate", "net_profit", "breakeven_win_rate", "edge_pp",
                  "max_drawdown_pct", "profit_factor", "verdict"):
            assert k in s

    def test_verdict_flags_small_sample(self, bt):
        r = bt.run(make_df(200), "rsi_reversal")
        if r.stats.total_trades < 30:
            assert "amostra insuficiente" in r.summary()["verdict"]

    def test_verdict_rejects_negative_edge(self, bt):
        r = bt.run(make_df(), "confluence")
        if r.stats.total_trades >= 30 and r.edge <= 0:
            assert "REPROVADA" in r.summary()["verdict"]

    def test_to_dict_is_serializable(self, bt):
        import json
        d = bt.run(make_df(), "confluence").to_dict()
        json.dumps(d)  # não deve levantar
        assert "summary" in d and "trades" in d and "equity_curve" in d

    def test_compare_ranks_by_profit(self, bt):
        results = bt.compare(make_df(), ALL)
        profits = [r.get("net_profit", float("-inf")) for r in results]
        assert profits == sorted(profits, reverse=True)
