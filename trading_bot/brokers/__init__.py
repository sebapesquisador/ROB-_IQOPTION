"""Fábrica de corretoras."""
from __future__ import annotations

from ..core.config import Broker as BrokerEnum
from .base import Broker, BrokerError, ConnectionError_, OrderRejected
from .paper import PaperBroker


def create_broker(settings) -> Broker:
    """Instancia a corretora conforme a configuração (import tardio por dependência opcional)."""
    kind = settings.broker

    if kind is BrokerEnum.PAPER:
        return PaperBroker(settings)

    if kind is BrokerEnum.IQOPTION:
        from .iqoption import IQOptionBroker
        return IQOptionBroker(settings)

    if kind is BrokerEnum.BINANCE:
        from .binance import BinanceBroker
        return BinanceBroker(settings)

    raise ValueError(f"Corretora desconhecida: {kind}")


__all__ = [
    "Broker", "BrokerError", "ConnectionError_", "OrderRejected",
    "PaperBroker", "create_broker",
]
