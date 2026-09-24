"""
Motor de execução.

Diferenças estruturais em relação ao `while True` do bot original:

  * Não bloqueia esperando resultado de ordem. Ordens abertas são
    verificadas a cada ciclo de forma assíncrona, então o robô nunca
    "cega" por 5 minutos enquanto uma operação está em curso.
  * Só avalia a estratégia UMA VEZ por candle fechado. O original
    rodava a estratégia a cada 1 segundo sobre o candle em formação,
    o que gerava sinais que apareciam e sumiam (repintura) e entradas
    duplicadas no mesmo candle.
  * Toda ordem passa pelo RiskManager antes de ser enviada.
  * Estado explícito (RUNNING/PAUSED/HALTED) controlável pela API.
  * Desligamento limpo com SIGINT/SIGTERM.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dtime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from ..brokers.base import Broker, BrokerError
from . import indicators
from .models import BotState, Direction, Order, OrderStatus, Signal
from .risk import RejectReason, RiskManager
from .storage import Storage
from .strategies import get_strategy
from .strategies.base import Strategy

logger = logging.getLogger(__name__)


class TradingEngine:
    """Orquestra corretora, estratégia, risco e persistência."""

    def __init__(self, settings, broker: Broker, storage: Optional[Storage] = None):
        self.settings = settings
        self.broker = broker
        self.storage = storage or Storage(settings.database_url)
        self.strategy = get_strategy(settings.strategy.name, settings.strategy)

        self.state = BotState.STOPPED
        self.risk: Optional[RiskManager] = None

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._open_orders: dict[str, Order] = {}
        self._last_evaluated_candle: Optional[pd.Timestamp] = None
        self._last_signal: Optional[Signal] = None
        self._last_error: Optional[str] = None
        self._active_symbol = settings.symbol
        self._cycles = 0
        self._started_at: Optional[datetime] = None
        self._listeners: list[Callable[[str, dict], None]] = []
        # Estratégia com saída própria rodando numa corretora que só fecha
        # no vencimento. Vira bandeira no painel para o operador não
        # confundir o que está rodando com o que foi testado.
        self._saida_nao_executada = False

    # ------------------------------------------------------------------ #
    # Eventos
    # ------------------------------------------------------------------ #

    def subscribe(self, fn: Callable[[str, dict], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, event: str, payload: dict) -> None:
        for fn in self._listeners:
            try:
                fn(event, payload)
            except Exception as exc:
                logger.debug("listener falhou: %s", exc)

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #

    def start(self) -> bool:
        with self._lock:
            if self.state is BotState.RUNNING:
                logger.warning("engine já está rodando")
                return False

            if not self.broker.is_connected and not self.broker.connect():
                self._last_error = "falha ao conectar na corretora"
                return False

            balance = self.broker.get_balance().balance
            if self.risk is None:
                self.risk = RiskManager(self.settings.risk, balance)
                # Retoma a contabilidade do dia após um restart
                pnl, trades = self.storage.today_pnl()
                if trades:
                    self.risk._book.realized_pnl = pnl
                    self.risk._book.trades = trades
                    self.risk._book.starting_balance = balance - pnl
                    logger.info("estado do dia recuperado: PnL %.2f em %d trades", pnl, trades)
            else:
                self.risk.sync_balance(balance)

            self._stop_event.clear()
            self.state = BotState.RUNNING
            self._started_at = datetime.now(timezone.utc)
            self._thread = threading.Thread(target=self._run, name="engine", daemon=True)
            self._thread.start()

            self.storage.log_event("INFO", "lifecycle", "robô iniciado", self.settings.masked())
            self._saida_nao_executada = self._avisar_sobre_saida_da_estrategia()
            logger.info("engine iniciado | %s | %s | saldo %.2f",
                        self.broker.name, self.strategy.name, balance)
            return True

    def stop(self, timeout: float = 15.0) -> None:
        with self._lock:
            if self.state is BotState.STOPPED:
                return
            logger.info("parando engine...")
            self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        with self._lock:
            self.state = BotState.STOPPED
            try:
                self.broker.disconnect()
            except Exception as exc:
                logger.debug("erro ao desconectar: %s", exc)
            self.storage.log_event("INFO", "lifecycle", "robô parado", self.snapshot())
            logger.info("engine parado")

    def pause(self) -> None:
        with self._lock:
            if self.state is BotState.RUNNING:
                self.state = BotState.PAUSED
                self.storage.log_event("INFO", "lifecycle", "robô pausado")
                logger.info("engine pausado")

    def resume(self) -> None:
        with self._lock:
            if self.state in (BotState.PAUSED, BotState.HALTED):
                self.state = BotState.RUNNING
                self.storage.log_event("INFO", "lifecycle", "robô retomado")
                logger.info("engine retomado")

    # ------------------------------------------------------------------ #
    # Loop principal
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                self._tick()
            except BrokerError as exc:
                self._last_error = str(exc)
                logger.error("erro de corretora: %s", exc)
                self.storage.log_event("ERROR", "broker", str(exc))
                self.broker.ensure_connected()
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("erro inesperado no ciclo")
                self.storage.log_event("ERROR", "engine", str(exc))

            elapsed = time.monotonic() - started
            self._stop_event.wait(max(0.5, self.settings.poll_interval_seconds - elapsed))

    def _avisar_sobre_saida_da_estrategia(self) -> bool:
        """A estratégia define saída própria que o motor ao vivo não executa?

        No backtest, `should_exit` fecha a posição. Ao vivo não existe esse
        caminho: a interface de corretora deste projeto abre ordem com
        vencimento e espera o resultado — nenhuma corretora aqui sabe
        encerrar uma posição antes da hora.

        Rodar assim não é errado, mas é uma estratégia DIFERENTE da que foi
        testada: as entradas são as mesmas, as saídas não. Isso precisa
        aparecer no log e no painel, nunca passar despercebido — a diferença
        entre backtest e operação real é exatamente onde o dinheiro some.
        """
        tipo = type(self.strategy)
        if getattr(tipo, "should_exit", Strategy.should_exit) is Strategy.should_exit:
            return False

        aviso = (
            f"A estratégia '{self.settings.strategy.name}' define regra de saída "
            f"própria (should_exit), mas a corretora '{self.settings.broker}' só "
            f"encerra posição no vencimento. As ENTRADAS seguem a estratégia; as "
            f"SAÍDAS, não. O resultado ao vivo vai divergir do backtest."
        )
        logger.warning(aviso)
        self.storage.log_event(
            "WARNING", "engine", "saída da estratégia não é executada ao vivo",
            {"strategy": self.settings.strategy.name, "broker": str(self.settings.broker)},
        )
        return True

    def _tick(self) -> None:
        self._cycles += 1

        # 1. Ordens abertas são sempre verificadas, mesmo pausado
        self._reconcile_open_orders()

        if self.state is not BotState.RUNNING:
            return

        # 2. Conexão viva?
        if not self.broker.ensure_connected():
            return

        # 3. Janela de negociação
        if not self._within_session():
            return

        # 4. Símbolo negociável agora
        symbol = self.broker.resolve_symbol(self.settings.symbol)
        if symbol != self._active_symbol:
            logger.info("símbolo ativo alterado: %s -> %s", self._active_symbol, symbol)
            self._active_symbol = symbol

        # 5. Candles
        df = self.broker.get_candles(
            symbol, self.settings.timeframe_minutes, self.settings.candles_lookback
        )
        if len(df) < 3:
            return

        # 6. Só avalia uma vez por candle FECHADO (evita repintura)
        last_closed_ts = df["timestamp"].iloc[-2]
        if self._last_evaluated_candle is not None and last_closed_ts <= self._last_evaluated_candle:
            return
        self._last_evaluated_candle = last_closed_ts

        # 7. Indicadores + sinal
        enriched = indicators.enrich(df, self.settings.strategy)
        signal = self.strategy.evaluate(enriched)
        self._last_signal = signal

        if not signal.is_actionable:
            logger.debug("sem sinal: %s", signal.reason)
            return

        logger.info("SINAL %s | confiança %.2f | %s",
                    signal.direction.value, signal.confidence, signal.reason)

        # 8. Risco
        decision = self.risk.approve(min_stake=self.broker.min_stake())
        if not decision:
            logger.warning("entrada bloqueada pelo risco: %s (%s)",
                           decision.reason.value, decision.detail)
            self.storage.log_event(
                "WARNING", "risk", decision.reason.value,
                {"detail": decision.detail, "signal": signal.direction.value},
            )
            if decision.reason in (
                RejectReason.DAILY_LOSS_LIMIT,
                RejectReason.DRAWDOWN_LIMIT,
                RejectReason.DAILY_TARGET_REACHED,
            ):
                self.state = BotState.HALTED
                logger.warning("robô TRAVADO: %s", decision.reason.value)
            return

        # 9. Execução
        self._execute(symbol, signal, decision.stake)

    # ------------------------------------------------------------------ #
    # Execução e reconciliação
    # ------------------------------------------------------------------ #

    def _execute(self, symbol: str, signal: Signal, stake: float) -> None:
        order = self.broker.place_order(
            symbol=symbol, direction=signal.direction, amount=stake,
            expiration_minutes=self.settings.expiration_minutes,
        )
        order.strategy = signal.strategy
        order.confidence = signal.confidence
        if not order.reason:
            order.reason = signal.reason

        self.storage.save_order(order)

        if order.status is OrderStatus.OPEN:
            self._open_orders[order.id] = order
            self.risk.register_open(order)
            self._emit("order_opened", order.to_dict())
            self.storage.log_event("INFO", "trade", "ordem aberta", order.to_dict())
        else:
            logger.warning("ordem não aberta: %s | %s", order.status.value, order.reason)
            self.storage.log_event("WARNING", "trade", "ordem recusada", order.to_dict())

    def _reconcile_open_orders(self) -> None:
        """Verifica ordens abertas sem bloquear o loop."""
        for oid, order in list(self._open_orders.items()):
            try:
                updated = self.broker.check_order(order)
            except Exception as exc:
                logger.debug("falha ao checar ordem %s: %s", oid, exc)
                continue

            if not updated.is_closed:
                continue

            self._open_orders.pop(oid, None)
            self.risk.register_close(updated)
            self.storage.save_order(updated)
            self.storage.record_equity(
                self.risk.current_balance, self.risk._book.realized_pnl
            )
            self._emit("order_closed", updated.to_dict())
            self.storage.log_event("INFO", "trade", "ordem fechada", updated.to_dict())

            logger.info(
                "RESULTADO %s | PnL %.2f | saldo %.2f | win rate %.1f%%",
                updated.status.value, updated.profit,
                self.risk.current_balance, self.risk.stats.win_rate,
            )

            # Sincroniza com o saldo real da corretora
            try:
                self.risk.sync_balance(self.broker.get_balance().balance)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Sessão
    # ------------------------------------------------------------------ #

    def _within_session(self) -> bool:
        cfg = self.settings.session
        try:
            tz = ZoneInfo(cfg.timezone)
        except Exception:
            tz = timezone.utc
        now = datetime.now(tz)

        if now.weekday() not in cfg.weekday_whitelist:
            if not (cfg.trade_on_weekends and now.weekday() >= 5):
                return False

        sh, sm = map(int, cfg.start_time.split(":"))
        eh, em = map(int, cfg.end_time.split(":"))
        start, end, current = dtime(sh, sm), dtime(eh, em), now.time()

        # Suporta janela que cruza a meia-noite (ex.: 22:00 -> 04:00)
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    # ------------------------------------------------------------------ #
    # Introspecção
    # ------------------------------------------------------------------ #

    def snapshot(self) -> dict:
        uptime = (
            (datetime.now(timezone.utc) - self._started_at).total_seconds()
            if self._started_at else 0
        )
        sig = self._last_signal
        return {
            "state": self.state.value,
            "broker": self.broker.name,
            "connected": self.broker.is_connected,
            "strategy": self.strategy.name,
            "symbol": self._active_symbol,
            "timeframe_minutes": self.settings.timeframe_minutes,
            "expiration_minutes": self.settings.expiration_minutes,
            "dry_run": self.settings.dry_run,
            "account_mode": self.settings.account_mode.value,
            "cycles": self._cycles,
            "uptime_seconds": int(uptime),
            "open_orders": len(self._open_orders),
            "last_error": self._last_error,
            "saida_da_estrategia_nao_executada": self._saida_nao_executada,
            "last_signal": {
                "direction": sig.direction.value,
                "confidence": round(sig.confidence, 3),
                "reason": sig.reason,
                "indicators": sig.indicators,
                "timestamp": sig.timestamp.isoformat(),
            } if sig else None,
            "risk": self.risk.snapshot() if self.risk else None,
        }
