"""
Indicadores técnicos vetorizados.

Correções importantes em relação à versão anterior do projeto:
  * RSI usa suavização de Wilder (EWM alpha=1/period), não média simples.
  * Divisão por zero tratada explicitamente (perda=0 => RSI=100).
  * ATR usa True Range completo, considerando gaps.
  * Todas as funções retornam Series alinhadas ao índice de entrada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI de Wilder.

    A implementação anterior usava rolling().mean(), o que produz valores
    diferentes dos das plataformas de trading e gera sinais dessincronizados.
    """
    if period < 2:
        raise ValueError("period deve ser >= 2")

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Suavização de Wilder
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))

    # perda média zero => mercado só subiu => RSI 100 (e vice-versa)
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return out.rename("rsi")


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean().rename(f"sma_{period}")


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, min_periods=period, adjust=False).mean().rename(f"ema_{period}")


def moving_average(series: pd.Series, period: int, kind: str = "EMA") -> pd.Series:
    kind = kind.upper()
    if kind == "EMA":
        return ema(series, period)
    if kind == "SMA":
        return sma(series, period)
    raise ValueError(f"Tipo de média desconhecido: {kind}")


def bollinger_bands(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Retorna (superior, média, inferior)."""
    middle = close.rolling(window=period, min_periods=period).mean()
    # ddof=0: desvio populacional, igual ao usado pelas plataformas gráficas
    std = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return (
        upper.rename("bb_upper"),
        middle.rename("bb_middle"),
        lower.rename("bb_lower"),
    )


def bollinger_percent_b(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.Series:
    """%B: posição relativa do preço dentro das bandas. 0 = banda inferior, 1 = superior."""
    upper, _, lower = bollinger_bands(close, period, num_std)
    width = (upper - lower).replace(0.0, np.nan)
    return ((close - lower) / width).rename("bb_percent_b")


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rename("true_range")


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range com suavização de Wilder."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().rename("atr")


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Retorna (linha macd, linha de sinal, histograma)."""
    ema_fast = close.ewm(span=fast, min_periods=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return (
        macd_line.rename("macd"),
        signal_line.rename("macd_signal"),
        histogram.rename("macd_hist"),
    )


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3
) -> tuple[pd.Series, pd.Series]:
    """Oscilador estocástico. Retorna (%K, %D)."""
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    denom = (highest - lowest).replace(0.0, np.nan)
    k = 100 * (close - lowest) / denom
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return k.rename("stoch_k"), d.rename("stoch_d")


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    ADX — força da tendência. Essencial como filtro:
    estratégias de reversão só funcionam com ADX baixo,
    estratégias de tendência só com ADX alto.
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )

    tr = true_range(high, low, close)
    alpha = 1.0 / period
    atr_s = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    plus_di = 100 * plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s.replace(0.0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr_s.replace(0.0, np.nan)

    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean().rename("adx")


def crossover(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """True no candle em que `fast` cruza `slow` para cima."""
    return (fast > slow) & (fast.shift(1) <= slow.shift(1))


def crossunder(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """True no candle em que `fast` cruza `slow` para baixo."""
    return (fast < slow) & (fast.shift(1) >= slow.shift(1))


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int = 14) -> pd.Series:
    """Williams %R: onde o fechamento está dentro da faixa do período.

        WPR = (maior máxima - fechamento) / (maior máxima - menor mínima) x -100

    Varia de -100 (fechou na mínima da janela) a 0 (fechou na máxima).
    Perto de -100 indica pressão vendedora exaurida; perto de 0, o oposto.

    Quando a janela inteira tem o mesmo preço, a divisão é 0/0. Nesse caso
    devolvemos -50 (o meio da faixa) em vez de NaN: um mercado parado não é
    dado ausente, e propagar NaN faria a estratégia perder candles bons
    depois que o mercado voltasse a andar.
    """
    maior = high.rolling(window=period, min_periods=period).max()
    menor = low.rolling(window=period, min_periods=period).min()
    faixa = maior - menor
    wpr = (maior - close) / faixa.replace(0.0, np.nan) * -100.0
    return wpr.where(faixa != 0, -50.0)


def enrich(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Anexa todos os indicadores configurados ao DataFrame de candles.
    Recebe um StrategyConfig. Retorna uma cópia — nunca muta o original.
    """
    out = df.copy()
    close, high, low = out["close"], out["high"], out["low"]

    out["rsi"] = rsi(close, cfg.rsi_period)
    out["ma_fast"] = moving_average(close, cfg.ma_fast_period, cfg.ma_type)
    out["ma_slow"] = moving_average(close, cfg.ma_slow_period, cfg.ma_type)

    upper, middle, lower = bollinger_bands(close, cfg.bb_period, cfg.bb_std)
    out["bb_upper"], out["bb_middle"], out["bb_lower"] = upper, middle, lower
    out["bb_percent_b"] = bollinger_percent_b(close, cfg.bb_period, cfg.bb_std)

    macd_line, macd_sig, macd_hist = macd(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd_line, macd_sig, macd_hist

    out["atr"] = atr(high, low, close, cfg.atr_period)
    out["atr_pct"] = (out["atr"] / close.replace(0.0, np.nan)) * 100
    out["adx"] = adx(high, low, close, cfg.atr_period)
    out["wpr"] = williams_r(high, low, close, cfg.wpr_period)

    return out
