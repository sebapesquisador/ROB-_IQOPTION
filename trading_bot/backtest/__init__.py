"""Backtesting."""
from .engine import Backtester, BacktestResult, BacktestTrade
from .funding_signal import alinhar, dividir, por_quantil, teste_permutacao
from .spot import SpotBacktester, SpotResult, SpotTrade

__all__ = [
    "Backtester", "BacktestResult", "BacktestTrade",
    "SpotBacktester", "SpotResult", "SpotTrade",
    "alinhar", "dividir", "por_quantil", "teste_permutacao",
]
