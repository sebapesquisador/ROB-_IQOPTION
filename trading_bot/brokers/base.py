"""Interface única de corretora. O engine não sabe com quem está falando."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from ..core.models import AccountBalance, Direction, Order

logger = logging.getLogger(__name__)


class BrokerError(Exception):
    """Erro genérico de corretora."""


class ConnectionError_(BrokerError):
    """Falha de conexão ou autenticação."""


class OrderRejected(BrokerError):
    """A corretora recusou a ordem."""


class Broker(ABC):
    """
    Contrato de corretora.

    Toda implementação deve devolver candles no MESMO formato normalizado:
    DataFrame com colunas [timestamp, open, high, low, close, volume],
    ordenado do mais antigo para o mais recente, sem duplicatas, e com
    o último candle podendo estar em formação.
    """

    name: str = "base"
    COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

    def __init__(self, settings):
        self.settings = settings
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ---- Ciclo de vida -------------------------------------------------

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    def ensure_connected(self) -> bool:
        """Reconecta se a sessão caiu. Chamado pelo engine a cada ciclo."""
        if self.is_connected and self.health_check():
            return True
        logger.warning("[%s] sessão inativa, reconectando...", self.name)
        self._connected = False
        return self.connect()

    def health_check(self) -> bool:
        return self._connected

    # ---- Dados ---------------------------------------------------------

    @abstractmethod
    def get_candles(self, symbol: str, timeframe_minutes: int, count: int) -> pd.DataFrame: ...

    @abstractmethod
    def get_balance(self) -> AccountBalance: ...

    def resolve_symbol(self, symbol: str) -> str:
        """Permite à corretora ajustar o símbolo (ex.: sufixo -OTC)."""
        return symbol

    def min_stake(self) -> float:
        return 1.0

    def payout(self, symbol: str) -> float:
        """Payout estimado (0.85 = 85%). Usado pelo engine e pelo backtest."""
        return 0.85

    # ---- Execução ------------------------------------------------------

    @abstractmethod
    def place_order(
        self, symbol: str, direction: Direction, amount: float, expiration_minutes: int
    ) -> Order: ...

    @abstractmethod
    def check_order(self, order: Order) -> Order:
        """Atualiza o status/resultado da ordem. Não bloqueia."""

    # ---- Normalização --------------------------------------------------

    @classmethod
    def normalize_candles(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Valida e padroniza o DataFrame de candles."""
        missing = [c for c in cls.COLUMNS if c not in df.columns]
        if missing:
            raise BrokerError(f"Colunas ausentes nos candles: {missing}")

        out = df[cls.COLUMNS].copy()
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
        for col in ("open", "high", "low", "close", "volume"):
            out[col] = pd.to_numeric(out[col], errors="coerce")

        out = out.dropna(subset=["open", "high", "low", "close"])
        out = out.drop_duplicates(subset="timestamp", keep="last")
        out = out.sort_values("timestamp").reset_index(drop=True)

        # Sanidade OHLC: high deve conter todos, low idem
        out["high"] = out[["high", "open", "close"]].max(axis=1)
        out["low"] = out[["low", "open", "close"]].min(axis=1)
        return out

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()
        return False
