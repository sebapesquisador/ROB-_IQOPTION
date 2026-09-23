"""
Corretora Binance (spot).

Diferença conceitual importante em relação à IQ Option: aqui não existe
"expiração". Uma posição spot é aberta com uma ordem de mercado e fechada
por stop loss / take profit. O adaptador traduz o modelo de Order do
projeto para esse mundo, registrando SL e TP como alvos monitorados.

Correções em relação ao bot_binance.py original:
  * Chaves de API vindas do .env, nunca do código.
  * Filtros do símbolo (LOT_SIZE, MIN_NOTIONAL, PRICE_FILTER) lidos da
    exchange e aplicados ao arredondar a quantidade — o original usava
    precisão fixa e as ordens eram recusadas.
  * recvWindow e sincronização de relógio, resolvendo o erro de timestamp
    documentado em ERRO_TIMESTAMP.md.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional

import pandas as pd

from ..core.models import AccountBalance, Direction, Order, OrderStatus
from .base import Broker, BrokerError, ConnectionError_, OrderRejected

logger = logging.getLogger(__name__)

_TF_MAP = {
    1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m",
    60: "1h", 120: "2h", 240: "4h", 360: "6h", 720: "12h", 1440: "1d",
}


class BinanceBroker(Broker):
    """Adaptador para a Binance Spot (mainnet ou testnet)."""

    name = "binance"

    def __init__(self, settings, stop_loss_pct: float = 1.0, take_profit_pct: float = 1.5):
        super().__init__(settings)
        self.client: Any = None
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self._filters: dict[str, dict] = {}
        self._time_offset = 0
        # Sem credenciais o adaptador ainda lê dados públicos, mas recusa ordens.
        self._read_only = False

    # ---- Ciclo de vida -------------------------------------------------

    # Valores de exemplo que o usuário pode ter copiado sem substituir.
    _PLACEHOLDERS = {
        "sua_chave", "seu_segredo", "sua_api_key", "seu_api_secret",
        "cole_sua_testnet_api_key_aqui", "cole_sua_testnet_secret_key_aqui",
        "cole_sua_mainnet_api_key_aqui", "cole_sua_mainnet_secret_key_aqui",
        "your_api_key", "your_api_secret", "changeme",
    }

    @classmethod
    def _e_placeholder(cls, valor: Optional[str]) -> bool:
        return bool(valor) and valor.strip().lower() in cls._PLACEHOLDERS

    def connect(self) -> bool:
        key, secret = self.settings.binance_api_key, self.settings.binance_api_secret

        if self._e_placeholder(key) or self._e_placeholder(secret):
            raise ConnectionError_(
                "BINANCE_API_KEY/BINANCE_API_SECRET ainda estão com o valor de "
                "exemplo do .env.example. Substitua pelas suas chaves reais — "
                "crie em https://testnet.binance.vision para a testnet."
            )

        # Dados de mercado (candles) são públicos na Binance: sem chave, o
        # adaptador ainda serve para backtest. Só a execução de ordens exige
        # credencial, e é onde a recusa acontece.
        if not (key and secret):
            self._read_only = True
            self._connected = True
            logger.info("[binance] conectado em modo SOMENTE LEITURA "
                        "(sem chaves: dados públicos, sem envio de ordens)")
            return True

        try:
            from binance.client import Client
        except ImportError as exc:
            raise ConnectionError_(
                "Biblioteca python-binance não instalada. "
                "Instale com: python -m pip install python-binance"
            ) from exc

        testnet = self.settings.binance_testnet or self.settings.account_mode.value == "demo"
        self.client = Client(key, secret, testnet=testnet)
        self.client.API_URL = (
            "https://testnet.binance.vision/api" if testnet
            else "https://api.binance.com/api"
        )

        try:
            # Corrige o erro recorrente de "Timestamp for this request is outside
            # of the recvWindow": alinha o relógio local ao servidor da Binance.
            server_time = self.client.get_server_time()["serverTime"]
            self._time_offset = server_time - int(time.time() * 1000)
            self.client.timestamp_offset = self._time_offset
            self.client.ping()
        except Exception as exc:
            raise ConnectionError_(f"Falha ao conectar na Binance: {exc}") from exc

        self._connected = True
        logger.info("[binance] conectado | %s | offset de relógio %dms",
                    "TESTNET" if testnet else "MAINNET", self._time_offset)
        if not testnet:
            logger.warning("[binance] ATENÇÃO: operando em MAINNET com dinheiro real")
        return True

    def disconnect(self) -> None:
        try:
            if self.client and hasattr(self.client, "close_connection"):
                self.client.close_connection()
        except Exception as exc:
            logger.debug("[binance] erro ao desconectar: %s", exc)
        finally:
            self._connected = False
            logger.info("[binance] desconectado")

    def health_check(self) -> bool:
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except Exception:
            return False

    # ---- Filtros do símbolo --------------------------------------------

    def _symbol_filters(self, symbol: str) -> dict:
        """Lê e cacheia LOT_SIZE / MIN_NOTIONAL / PRICE_FILTER da exchange."""
        if symbol in self._filters:
            return self._filters[symbol]

        try:
            info = self.client.get_symbol_info(symbol)
        except Exception as exc:
            raise BrokerError(f"Falha ao obter info de {symbol}: {exc}") from exc
        if not info:
            raise BrokerError(f"Símbolo {symbol} não existe na Binance")

        parsed = {"step_size": 1e-8, "min_qty": 0.0, "min_notional": 0.0, "tick_size": 1e-8}
        for f in info.get("filters", []):
            ftype = f["filterType"]
            if ftype == "LOT_SIZE":
                parsed["step_size"] = float(f["stepSize"])
                parsed["min_qty"] = float(f["minQty"])
            elif ftype in ("MIN_NOTIONAL", "NOTIONAL"):
                parsed["min_notional"] = float(f.get("minNotional", 0))
            elif ftype == "PRICE_FILTER":
                parsed["tick_size"] = float(f["tickSize"])

        self._filters[symbol] = parsed
        return parsed

    @staticmethod
    def _round_step(value: float, step: float) -> float:
        """Arredonda para baixo ao múltiplo do step, sem erro de ponto flutuante."""
        if step <= 0:
            return value
        return float(
            (Decimal(str(value)) // Decimal(str(step))) * Decimal(str(step))
        )

    # ---- Dados ---------------------------------------------------------

    # Candles sempre da mainnet: o histórico da testnet é gerado por um motor
    # de testes com liquidez artificial e não reflete o mercado real. Um
    # backtest sobre esses dados mede ficção. A testnet continua valendo para
    # testar execução de ordens, que é o que ela existe para fazer.
    _PUBLIC_KLINES = "https://api.binance.com/api/v3/klines"
    _MAX_PER_REQUEST = 1000

    def _fetch_klines_publico(self, symbol: str, interval: str,
                              limit: int, end_ms: Optional[int] = None) -> list:
        """Lê klines pelo endpoint público, sem exigir credencial."""
        import json
        import urllib.error
        import urllib.parse
        import urllib.request

        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        if end_ms is not None:
            params["endTime"] = end_ms
        url = f"{self._PUBLIC_KLINES}?{urllib.parse.urlencode(params)}"

        ultimo: Exception | None = None
        for tentativa in range(1, 4):
            try:
                with urllib.request.urlopen(url, timeout=20) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                corpo = exc.read().decode("utf-8", "replace")[:200]
                if exc.code == 400 and "Invalid symbol" in corpo:
                    raise BrokerError(
                        f"Símbolo '{symbol}' não existe na Binance. "
                        "Use o formato sem barra, como BTCUSDT ou ETHUSDT."
                    ) from exc
                ultimo = exc
            except Exception as exc:
                ultimo = exc
            if tentativa < 3:
                time.sleep(tentativa)
        raise BrokerError(f"Falha ao obter klines de {symbol}: {ultimo}")

    def get_candles(self, symbol: str, timeframe_minutes: int, count: int) -> pd.DataFrame:
        interval = _TF_MAP.get(timeframe_minutes)
        if interval is None:
            raise BrokerError(
                f"Timeframe {timeframe_minutes}min não suportado. "
                f"Use um de: {sorted(_TF_MAP)}"
            )

        # Pagina para trás até completar o pedido. Truncar em 1000 sem avisar
        # foi exatamente o bug que distorceu os backtests da IQ Option.
        restante = count
        fim_ms: Optional[int] = None
        paginas: list[list] = []
        mais_antigo_visto: Optional[int] = None

        while restante > 0:
            lote_tam = min(restante, self._MAX_PER_REQUEST)
            lote = self._fetch_klines_publico(symbol, interval, lote_tam, fim_ms)
            if not lote:
                break

            paginas.append(lote)
            restante -= len(lote)

            mais_antigo = int(lote[0][0])
            if mais_antigo_visto is not None and mais_antigo >= mais_antigo_visto:
                break  # a API parou de retroceder
            mais_antigo_visto = mais_antigo
            fim_ms = mais_antigo - 1

            if len(lote) < lote_tam:
                break  # histórico esgotado

        if not paginas:
            raise BrokerError(f"Nenhum kline retornado para {symbol}")

        unicos: dict[int, list] = {}
        for lote in paginas:
            for k in lote:
                unicos[int(k[0])] = k
        ordenados = [unicos[t] for t in sorted(unicos)][-count:]

        if len(ordenados) < count:
            logger.info("[binance] %s: %d candles disponíveis (pedidos %d)",
                        symbol, len(ordenados), count)

        df = pd.DataFrame(ordenados, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_base", "taker_quote", "ignore",
        ])
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        return self.normalize_candles(df)

    def get_balance(self) -> AccountBalance:
        quote = "USDT"
        try:
            acct = self.client.get_account()
            for bal in acct["balances"]:
                if bal["asset"] == quote:
                    return AccountBalance(
                        balance=float(bal["free"]), currency=quote,
                        mode="testnet" if self.settings.binance_testnet else "real",
                    )
        except Exception as exc:
            raise BrokerError(f"Falha ao obter saldo: {exc}") from exc
        return AccountBalance(balance=0.0, currency=quote)

    def payout(self, symbol: str) -> float:
        """Em spot não existe payout fixo; usa a razão TP/SL como proxy."""
        return self.take_profit_pct / max(self.stop_loss_pct, 0.01)

    def min_stake(self) -> float:
        return 10.0  # mínimo típico de notional na Binance

    # ---- Execução ------------------------------------------------------

    def place_order(
        self, symbol: str, direction: Direction, amount: float, expiration_minutes: int
    ) -> Order:
        order = Order(
            symbol=symbol, direction=direction, amount=amount,
            expiration_minutes=expiration_minutes,
        )

        if self._read_only or self.client is None:
            order.status = OrderStatus.REJECTED
            order.reason = (
                "modo somente leitura: configure BINANCE_API_KEY e "
                "BINANCE_API_SECRET no .env para enviar ordens"
            )
            logger.warning("[binance] %s", order.reason)
            return order

        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            price = float(ticker["price"])
        except Exception as exc:
            order.status = OrderStatus.ERROR
            order.reason = f"falha ao obter preço: {exc}"
            return order

        filters = self._symbol_filters(symbol)
        qty = self._round_step(amount / price, filters["step_size"])

        if qty < filters["min_qty"]:
            order.status = OrderStatus.REJECTED
            order.reason = f"quantidade {qty} abaixo do mínimo {filters['min_qty']}"
            logger.warning("[binance] %s", order.reason)
            return order
        if qty * price < filters["min_notional"]:
            order.status = OrderStatus.REJECTED
            order.reason = (
                f"notional {qty * price:.2f} abaixo do mínimo {filters['min_notional']}"
            )
            logger.warning("[binance] %s", order.reason)
            return order

        order.entry_price = price
        order.metadata.update({
            "quantity": qty,
            "stop_loss": price * (1 - self.stop_loss_pct / 100) if direction is Direction.CALL
                         else price * (1 + self.stop_loss_pct / 100),
            "take_profit": price * (1 + self.take_profit_pct / 100) if direction is Direction.CALL
                           else price * (1 - self.take_profit_pct / 100),
        })

        if self.settings.dry_run:
            order.status = OrderStatus.OPEN
            order.dry_run = True
            order.broker_order_id = f"dry-{order.id[:8]}"
            logger.info("[binance][DRY-RUN] %s %s qty=%s @ %.4f",
                        order.broker_order_id, direction.value, qty, price)
            return order

        # Spot não permite venda a descoberto: PUT só fecha posição existente.
        if direction is Direction.PUT:
            order.status = OrderStatus.REJECTED
            order.reason = "venda a descoberto não suportada em spot; sinal PUT ignorado"
            logger.info("[binance] %s", order.reason)
            return order

        try:
            from binance.enums import ORDER_TYPE_MARKET, SIDE_BUY
            result = self.client.create_order(
                symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty
            )
        except Exception as exc:
            order.status = OrderStatus.ERROR
            order.reason = f"corretora recusou a ordem: {exc}"
            logger.error("[binance] %s", order.reason)
            return order

        order.broker_order_id = str(result.get("orderId"))
        order.status = OrderStatus.OPEN
        fills = result.get("fills") or []
        if fills:
            total_qty = sum(float(f["qty"]) for f in fills)
            order.entry_price = sum(
                float(f["price"]) * float(f["qty"]) for f in fills
            ) / max(total_qty, 1e-12)

        logger.info("[binance] ordem %s executada | qty=%s @ %.4f",
                    order.broker_order_id, qty, order.entry_price)
        return order

    def check_order(self, order: Order) -> Order:
        """Fecha a posição ao atingir SL ou TP."""
        if order.is_closed:
            return order

        try:
            price = float(self.client.get_symbol_ticker(symbol=order.symbol)["price"])
        except Exception as exc:
            logger.debug("[binance] preço indisponível: %s", exc)
            return order

        sl = order.metadata.get("stop_loss")
        tp = order.metadata.get("take_profit")
        qty = order.metadata.get("quantity", 0.0)
        entry = order.entry_price or price

        hit_tp = price >= tp if order.direction is Direction.CALL else price <= tp
        hit_sl = price <= sl if order.direction is Direction.CALL else price >= sl
        if not (hit_tp or hit_sl):
            return order

        if not order.dry_run:
            try:
                from binance.enums import ORDER_TYPE_MARKET, SIDE_SELL
                self.client.create_order(
                    symbol=order.symbol, side=SIDE_SELL,
                    type=ORDER_TYPE_MARKET, quantity=qty,
                )
            except Exception as exc:
                logger.error("[binance] falha ao fechar posição: %s", exc)
                return order

        order.exit_price = price
        order.closed_at = datetime.now(timezone.utc)
        pnl = (price - entry) * qty
        if order.direction is Direction.PUT:
            pnl = -pnl
        order.profit = pnl
        order.status = OrderStatus.WON if pnl > 0 else (
            OrderStatus.LOST if pnl < 0 else OrderStatus.TIE
        )
        logger.info("[binance] ordem %s -> %s | PnL %.2f (%s)",
                    order.broker_order_id, order.status.value, pnl,
                    "TP" if hit_tp else "SL")
        return order
