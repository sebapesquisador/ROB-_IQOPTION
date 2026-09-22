"""
Interface base das estratégias e registro dinâmico.

No projeto original cada estratégia era um método gigante que chamava
`abrir_posicao()` diretamente — misturando decisão, risco e execução.
Aqui a estratégia faz UMA coisa: recebe candles e devolve um Signal.
Quem executa é o engine, depois de passar pelo risk manager.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, Type

import pandas as pd

from ..models import Direction, Signal

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Type["Strategy"]] = {}


def register(name: str) -> Callable[[Type["Strategy"]], Type["Strategy"]]:
    """Decorator que registra uma estratégia pelo nome."""
    def wrapper(cls: Type["Strategy"]) -> Type["Strategy"]:
        key = name.lower()
        if key in _REGISTRY:
            raise ValueError(f"Estratégia '{name}' já registrada")
        cls.name = key
        _REGISTRY[key] = cls
        return cls
    return wrapper


def get_strategy(name: str, config) -> "Strategy":
    key = name.lower()
    if key not in _REGISTRY:
        disponiveis = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Estratégia '{name}' não existe. Disponíveis: {disponiveis}")
    return _REGISTRY[key](config)


def available_strategies() -> list[dict[str, str]]:
    return [
        {"name": n, "description": (c.__doc__ or "").strip().split("\n")[0]}
        for n, c in sorted(_REGISTRY.items())
    ]


class Strategy(ABC):
    """
    Contrato de uma estratégia.

    Invariantes que TODA estratégia deve respeitar:
      1. Nunca usar o candle em formação (índice -1) para decidir entrada.
         Ele ainda vai mudar; usar o candle -1 é repintura e destrói o
         backtest. Use sempre `df.iloc[-2]` como último candle fechado.
      2. Ser pura: não envia ordens, não muta estado externo.
      3. Devolver confiança calibrada entre 0 e 1.
    """

    name: str = "base"
    min_candles: int = 50

    def __init__(self, config):
        self.cfg = config

    # ---- API pública ---------------------------------------------------

    def evaluate(self, df: pd.DataFrame) -> Signal:
        """Valida os dados, aplica filtros globais e delega para `generate`."""
        if df is None or len(df) < max(self.min_candles, self.required_candles()):
            return Signal.none(self.name, "candles insuficientes")

        if df[["open", "high", "low", "close"]].iloc[-2:].isna().any().any():
            return Signal.none(self.name, "dados incompletos nos últimos candles")

        signal = self.generate(df)

        if not signal.is_actionable:
            return signal

        # Filtro de volatilidade — evita operar em mercado morto ou em pânico
        atr_pct = df["atr_pct"].iloc[-2] if "atr_pct" in df.columns else None
        if atr_pct is not None and pd.notna(atr_pct):
            signal.indicators["atr_pct"] = round(float(atr_pct), 4)
            if atr_pct < self.cfg.min_atr_pct:
                return Signal.none(self.name, f"volatilidade baixa demais (ATR {atr_pct:.3f}%)")
            if atr_pct > self.cfg.max_atr_pct:
                return Signal.none(self.name, f"volatilidade alta demais (ATR {atr_pct:.3f}%)")

        # Filtro de confiança mínima
        if signal.confidence < self.cfg.min_confidence:
            return Signal.none(
                self.name,
                f"confiança {signal.confidence:.2f} < mínimo {self.cfg.min_confidence:.2f}",
            )

        return signal

    # ---- A implementar -------------------------------------------------

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> Signal:
        """Produz o sinal. `df` já vem enriquecido com indicadores."""

    def required_candles(self) -> int:
        """Quantidade mínima de candles para os indicadores estabilizarem."""
        return max(
            self.cfg.rsi_period, self.cfg.ma_slow_period,
            self.cfg.bb_period, self.cfg.macd_slow, self.cfg.atr_period,
        ) + 10

    # ---- Helpers para subclasses --------------------------------------

    @staticmethod
    def last_closed(df: pd.DataFrame) -> pd.Series:
        """Último candle FECHADO. Nunca use iloc[-1] para decidir."""
        return df.iloc[-2]

    @staticmethod
    def previous_closed(df: pd.DataFrame) -> pd.Series:
        return df.iloc[-3]

    def trend_direction(self, row: pd.Series) -> Direction:
        """Direção da tendência segundo a MA lenta."""
        if pd.isna(row.get("ma_slow")):
            return Direction.NONE
        if row["close"] > row["ma_slow"]:
            return Direction.CALL
        if row["close"] < row["ma_slow"]:
            return Direction.PUT
        return Direction.NONE

    def trend_ok(self, row: pd.Series, direction: Direction) -> bool:
        """Verifica alinhamento com a tendência, se exigido pela config."""
        if not self.cfg.require_trend_alignment:
            return True
        return self.trend_direction(row) is direction
