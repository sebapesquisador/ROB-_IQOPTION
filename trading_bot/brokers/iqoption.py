"""
Corretora IQ Option.

Correções em relação à implementação original:

  * Credenciais vêm da configuração (.env), não hardcoded no fonte.
  * Disponibilidade de ativo é consultada de verdade via get_all_open_time()
    e cacheada, em vez de "tenta binary, se der erro tenta digital, se der
    erro tenta 1/2/5 minutos" — aquele fallback em cascata enviava ordens
    com expiração diferente da pedida pela estratégia, o que invalida o
    resultado do trade.
  * `check_order` é NÃO bloqueante. A versão anterior travava o loop
    inteiro por até 300 segundos dentro de `verificar_resultado_operacao`,
    fazendo o robô perder todos os candles do período.
  * Reconexão automática com backoff exponencial.
  * Timestamps tratados como UTC-aware, corrigindo o bug de fuso.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

from ..core.models import AccountBalance, Direction, Order, OrderStatus
from .base import Broker, BrokerError, ConnectionError_, OrderRejected

logger = logging.getLogger(__name__)


class IQOptionBroker(Broker):
    """Adaptador para a API não oficial da IQ Option."""

    name = "iqoption"
    _ASSET_CACHE_TTL = 300  # segundos

    def __init__(self, settings):
        super().__init__(settings)
        self.api: Any = None
        self._asset_cache: dict[str, Any] = {}
        self._asset_cache_at: float = 0.0
        self._reconnect_attempts = 0

    # ---- Ciclo de vida -------------------------------------------------

    def connect(self) -> bool:
        try:
            from iqoptionapi.stable_api import IQ_Option  # import tardio: dependência opcional
        except ImportError as exc:
            raise ConnectionError_(
                "Biblioteca iqoptionapi não instalada. "
                "Instale com: pip install -r requirements.txt"
            ) from exc

        email = self.settings.iq_email
        password = self.settings.iq_password
        if not (email and password):
            raise ConnectionError_(
                "IQ_EMAIL e IQ_PASSWORD não configurados. Defina-os no arquivo .env"
            )

        logger.info("[iq] conectando como %s...", email[:3] + "***")
        self.api = IQ_Option(email, password)
        ok, reason = self.api.connect()

        if not ok:
            self._connected = False
            raise ConnectionError_(f"Falha na conexão com a IQ Option: {reason}")

        balance_type = "PRACTICE" if self.settings.account_mode.value == "demo" else "REAL"
        self.api.change_balance(balance_type)
        self._connected = True
        self._reconnect_attempts = 0

        bal = self.get_balance()
        logger.info("[iq] conectado | conta %s | saldo %.2f %s",
                    balance_type, bal.balance, bal.currency)
        if balance_type == "REAL":
            logger.warning("[iq] ATENÇÃO: operando em CONTA REAL com dinheiro de verdade")
        return True

    def disconnect(self) -> None:
        try:
            if self.api is not None:
                for closer in ("close", "close_connect", "api.close"):
                    obj = self.api
                    for part in closer.split("."):
                        obj = getattr(obj, part, None)
                        if obj is None:
                            break
                    if callable(obj):
                        obj()
                        break
        except Exception as exc:
            logger.debug("[iq] erro ao desconectar: %s", exc)
        finally:
            self._connected = False
            logger.info("[iq] desconectado")

    def health_check(self) -> bool:
        if not self.api:
            return False
        try:
            return bool(self.api.check_connect())
        except Exception:
            return False

    def ensure_connected(self) -> bool:
        """Reconexão com backoff exponencial, limitado a 60s entre tentativas."""
        if self.health_check():
            self._connected = True
            return True

        self._connected = False
        delay = min(2 ** self._reconnect_attempts, 60)
        self._reconnect_attempts += 1
        logger.warning("[iq] conexão perdida. Tentativa %d em %ds", self._reconnect_attempts, delay)
        time.sleep(delay)
        try:
            return self.connect()
        except Exception as exc:
            logger.error("[iq] falha ao reconectar: %s", exc)
            return False

    # ---- Ativos --------------------------------------------------------

    def _open_assets(self, force: bool = False) -> dict:
        """Lista de ativos abertos, com cache de 5 minutos."""
        now = time.time()
        if not force and self._asset_cache and (now - self._asset_cache_at) < self._ASSET_CACHE_TTL:
            return self._asset_cache
        try:
            self._asset_cache = self.api.get_all_open_time() or {}
            self._asset_cache_at = now
        except Exception as exc:
            logger.warning("[iq] falha ao listar ativos: %s", exc)
        return self._asset_cache

    def _is_open(self, symbol: str, market: str = "binary") -> bool:
        assets = self._open_assets()
        info = assets.get(market, {}).get(symbol)
        return bool(info and info.get("open"))

    def resolve_symbol(self, symbol: str) -> str:
        """
        Escolhe entre o par normal e a versão OTC com base na
        disponibilidade REAL informada pela corretora.

        A versão anterior decidia por regra de horário chutada no código
        ("if hora < 13 or hora >= 20"), que estava errada e forçava OTC
        durante o pregão aberto.
        """
        base = symbol.replace("-OTC", "")
        if self._is_open(base, "binary") or self._is_open(base, "turbo"):
            return base

        otc = f"{base}-OTC"
        if self.settings.auto_otc and (self._is_open(otc, "binary") or self._is_open(otc, "turbo")):
            logger.info("[iq] %s fechado, usando %s", base, otc)
            return otc

        # Nenhum dos dois aberto: devolve o pedido e deixa o engine pular o ciclo
        logger.warning("[iq] nem %s nem %s estão abertos", base, otc)
        return base

    def is_tradable(self, symbol: str) -> bool:
        return self._is_open(symbol, "binary") or self._is_open(symbol, "turbo")

    def payout(self, symbol: str) -> float:
        try:
            profits = self.api.get_all_profit()
            entry = profits.get(symbol, {})
            value = entry.get("turbo") or entry.get("binary")
            if value:
                return float(value)
        except Exception as exc:
            logger.debug("[iq] payout indisponível para %s: %s", symbol, exc)
        return 0.80

    def min_stake(self) -> float:
        return 1.0

    # ---- Dados ---------------------------------------------------------

    def get_candles(self, symbol: str, timeframe_minutes: int, count: int) -> pd.DataFrame:
        if not self.api:
            raise BrokerError("API não conectada")

        tf_seconds = timeframe_minutes * 60
        count = min(count, 1000)  # limite da API

        try:
            raw = self.api.get_candles(symbol, tf_seconds, count, time.time())
        except Exception as exc:
            raise BrokerError(f"Falha ao obter candles de {symbol}: {exc}") from exc

        if not raw:
            raise BrokerError(f"Nenhum candle retornado para {symbol}")

        df = pd.DataFrame(raw)

        # A API usa 'from'/'at' para o timestamp e 'min'/'max' para low/high
        ts_col = "from" if "from" in df.columns else ("at" if "at" in df.columns else None)
        if ts_col is None:
            raise BrokerError("Candles sem coluna de timestamp reconhecível")
        # 'at' vem em nanossegundos em algumas versões da API
        unit = "ns" if ts_col == "at" and df[ts_col].iloc[0] > 1e15 else "s"
        df["timestamp"] = pd.to_datetime(df[ts_col], unit=unit, utc=True)

        rename = {}
        if "min" in df.columns:
            rename["min"] = "low"
        if "max" in df.columns:
            rename["max"] = "high"
        df = df.rename(columns=rename)

        for col, fallback in (("high", "close"), ("low", "close"), ("volume", None)):
            if col not in df.columns:
                df[col] = df[fallback] if fallback else 0.0

        return self.normalize_candles(df)

    def get_balance(self) -> AccountBalance:
        try:
            balance = float(self.api.get_balance())
            currency = self.api.get_currency() if hasattr(self.api, "get_currency") else "USD"
        except Exception as exc:
            raise BrokerError(f"Falha ao obter saldo: {exc}") from exc
        return AccountBalance(
            balance=balance, currency=currency, mode=self.settings.account_mode.value
        )

    # ---- Execução ------------------------------------------------------

    def place_order(
        self, symbol: str, direction: Direction, amount: float, expiration_minutes: int
    ) -> Order:
        if direction is Direction.NONE:
            raise OrderRejected("Direção inválida para ordem")

        order = Order(
            symbol=symbol, direction=direction, amount=amount,
            expiration_minutes=expiration_minutes,
        )

        if self.settings.dry_run:
            order.status = OrderStatus.OPEN
            order.dry_run = True
            order.broker_order_id = f"dry-{order.id[:8]}"
            try:
                order.entry_price = float(
                    self.get_candles(symbol, self.settings.timeframe_minutes, 2)["close"].iloc[-1]
                )
            except Exception:
                order.entry_price = None
            order.metadata["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)
            ).isoformat()
            logger.info("[iq][DRY-RUN] ordem simulada %s %s $%.2f",
                        order.broker_order_id, direction.value, amount)
            return order

        if not self.is_tradable(symbol):
            order.status = OrderStatus.REJECTED
            order.reason = f"{symbol} não está disponível para negociação agora"
            logger.warning("[iq] %s", order.reason)
            return order

        action = "call" if direction is Direction.CALL else "put"
        try:
            ok, oid = self.api.buy(amount, symbol, action, expiration_minutes)
        except Exception as exc:
            order.status = OrderStatus.ERROR
            order.reason = f"exceção ao enviar ordem: {exc}"
            logger.error("[iq] %s", order.reason)
            return order

        if not ok or not oid:
            order.status = OrderStatus.REJECTED
            order.reason = f"corretora recusou a ordem: {oid}"
            logger.warning("[iq] %s", order.reason)
            return order

        order.broker_order_id = str(oid)
        order.status = OrderStatus.OPEN
        order.metadata["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)
        ).isoformat()
        logger.info("[iq] ordem %s enviada | %s $%.2f | exp %dmin",
                    order.broker_order_id, direction.value, amount, expiration_minutes)
        return order

    def check_order(self, order: Order) -> Order:
        """
        Verificação NÃO bloqueante. Retorna imediatamente se ainda não expirou;
        o engine continua processando candles enquanto a ordem está aberta.
        """
        if order.is_closed:
            return order

        expires_at_raw = order.metadata.get("expires_at")
        if expires_at_raw:
            expires_at = datetime.fromisoformat(expires_at_raw)
            if datetime.now(timezone.utc) < expires_at:
                return order

        if order.dry_run:
            return self._resolve_dry_run(order)

        try:
            # check_win_v3 pode devolver None enquanto a ordem não liquidou
            profit = self.api.check_win_v3(int(order.broker_order_id))
        except Exception as exc:
            logger.debug("[iq] resultado ainda indisponível para %s: %s",
                         order.broker_order_id, exc)
            return order

        if profit is None:
            return order

        profit = float(profit)
        order.profit = profit
        order.closed_at = datetime.now(timezone.utc)
        if profit > 0:
            order.status = OrderStatus.WON
        elif profit < 0:
            order.status = OrderStatus.LOST
        else:
            order.status = OrderStatus.TIE

        logger.info("[iq] ordem %s -> %s | PnL $%.2f",
                    order.broker_order_id, order.status.value, profit)
        return order

    def _resolve_dry_run(self, order: Order) -> Order:
        """Liquida ordem simulada usando o preço real de mercado."""
        try:
            exit_price = float(
                self.get_candles(order.symbol, self.settings.timeframe_minutes, 2)["close"].iloc[-1]
            )
        except Exception as exc:
            logger.warning("[iq][DRY-RUN] sem preço para liquidar: %s", exc)
            return order

        order.exit_price = exit_price
        order.closed_at = datetime.now(timezone.utc)
        entry = order.entry_price or exit_price

        if exit_price == entry:
            order.status, order.profit = OrderStatus.TIE, 0.0
        else:
            won = (order.direction is Direction.CALL) == (exit_price > entry)
            if won:
                order.status = OrderStatus.WON
                order.profit = order.amount * self.payout(order.symbol)
            else:
                order.status = OrderStatus.LOST
                order.profit = -order.amount

        logger.info("[iq][DRY-RUN] ordem %s -> %s | PnL $%.2f",
                    order.broker_order_id, order.status.value, order.profit)
        return order
