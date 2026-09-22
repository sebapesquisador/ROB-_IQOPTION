"""Registro de estratégias."""
from .base import Strategy, available_strategies, get_strategy, register
from . import builtin  # noqa: F401  — registra as estratégias embutidas

__all__ = ["Strategy", "get_strategy", "register", "available_strategies"]
