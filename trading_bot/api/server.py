"""
API + painel de controle.

O painel antigo era só leitura: o bot fazia POST de números num JSON e a
página exibia. Não dava para iniciar, parar, trocar estratégia nem ver por
que uma entrada foi bloqueada. Aqui o painel CONTROLA o robô de verdade,
com autenticação nos endpoints de escrita e streaming de eventos por SSE.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ..backtest import Backtester
from ..brokers import create_broker
from ..core.config import get_settings
from ..core.engine import TradingEngine
from ..core.models import BotState
from ..core.storage import Storage
from ..core.strategies import available_strategies

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent

_engine: Optional[TradingEngine] = None
_event_queues: list[asyncio.Queue] = []
_loop: Optional[asyncio.AbstractEventLoop] = None


def get_engine() -> TradingEngine:
    if _engine is None:
        raise HTTPException(status_code=503, detail="engine não inicializado")
    return _engine


def require_token(request: Request) -> None:
    """Protege endpoints de escrita. Sem token configurado, libera (modo local)."""
    settings = get_settings()
    token = (settings.api_token or "").strip()
    if not token:
        return  # sem token configurado = uso local, sem autenticação
    provided = (
        request.headers.get("X-API-Token") or request.query_params.get("token") or ""
    ).strip()
    if provided != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token inválido")


def _broadcast(event: str, payload: dict) -> None:
    """Chamado pelo engine (thread separada) para empurrar eventos ao painel."""
    if _loop is None:
        return
    msg = {"event": event, "data": payload, "ts": datetime.now(timezone.utc).isoformat()}
    for q in list(_event_queues):
        try:
            _loop.call_soon_threadsafe(q.put_nowait, msg)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _loop
    _loop = asyncio.get_running_loop()
    settings = get_settings()
    broker = create_broker(settings)
    _engine = TradingEngine(settings, broker, Storage(settings.database_url))
    _engine.subscribe(_broadcast)
    logger.info("API pronta | corretora=%s | estratégia=%s",
                settings.broker.value, settings.strategy.name)
    yield
    if _engine and _engine.state is not BotState.STOPPED:
        _engine.stop()


app = FastAPI(
    title="Trading Bot — Painel de Controle",
    description="API de controle e monitoramento do robô de trading",
    version="2.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class ConfigUpdate(BaseModel):
    symbol: Optional[str] = None
    timeframe_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    expiration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    strategy: Optional[str] = None
    dry_run: Optional[bool] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    percent_stake: Optional[float] = Field(default=None, gt=0, le=5.0)
    fixed_stake: Optional[float] = Field(default=None, gt=0)
    sizing_mode: Optional[str] = None
    max_daily_loss_pct: Optional[float] = Field(default=None, gt=0, le=50)
    max_consecutive_losses: Optional[int] = Field(default=None, ge=1)
    daily_profit_target_pct: Optional[float] = Field(default=None, gt=0)


class BacktestRequest(BaseModel):
    strategies: Optional[list[str]] = None
    candles: int = Field(default=1000, ge=100, le=5000)
    payout: float = Field(default=0.85, gt=0, le=2.0)
    initial_balance: float = Field(default=1000.0, gt=0)
    min_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    expiration_candles: int = Field(default=1, ge=1, le=20)


# --------------------------------------------------------------------------- #
# Painel
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "engine": _engine.state.value if _engine else "uninitialized"}


# --------------------------------------------------------------------------- #
# Estado e controle
# --------------------------------------------------------------------------- #

@app.get("/api/status")
async def get_status(engine: TradingEngine = Depends(get_engine)):
    return engine.snapshot()


@app.get("/api/config")
async def get_config(engine: TradingEngine = Depends(get_engine)):
    s = engine.settings
    return {
        **s.masked(),
        "strategies_available": available_strategies(),
        "risk": s.risk.model_dump(),
        "strategy_params": s.strategy.model_dump(),
        "session": s.session.model_dump(),
    }


@app.post("/api/control/start", dependencies=[Depends(require_token)])
async def start_bot(engine: TradingEngine = Depends(get_engine)):
    if engine.settings.is_live:
        logger.warning("iniciando em MODO REAL")
    ok = engine.start()
    if not ok and engine.state is not BotState.RUNNING:
        raise HTTPException(400, detail=engine._last_error or "falha ao iniciar")
    return {"ok": True, "state": engine.state.value}


@app.post("/api/control/stop", dependencies=[Depends(require_token)])
async def stop_bot(engine: TradingEngine = Depends(get_engine)):
    await asyncio.to_thread(engine.stop)
    return {"ok": True, "state": engine.state.value}


@app.post("/api/control/pause", dependencies=[Depends(require_token)])
async def pause_bot(engine: TradingEngine = Depends(get_engine)):
    engine.pause()
    return {"ok": True, "state": engine.state.value}


@app.post("/api/control/resume", dependencies=[Depends(require_token)])
async def resume_bot(engine: TradingEngine = Depends(get_engine)):
    engine.resume()
    return {"ok": True, "state": engine.state.value}


@app.patch("/api/config", dependencies=[Depends(require_token)])
async def update_config(payload: ConfigUpdate, engine: TradingEngine = Depends(get_engine)):
    """Altera configuração em runtime. Exige robô parado para trocar estratégia/mercado."""
    s = engine.settings
    structural = any([
        payload.symbol, payload.timeframe_minutes, payload.expiration_minutes, payload.strategy,
    ])
    if structural and engine.state is BotState.RUNNING:
        raise HTTPException(409, detail="pare o robô antes de alterar mercado ou estratégia")

    changed: dict[str, Any] = {}

    if payload.symbol:
        s.symbol = payload.symbol.upper()
        engine._active_symbol = s.symbol
        changed["symbol"] = s.symbol
    if payload.timeframe_minutes:
        s.timeframe_minutes = payload.timeframe_minutes
        changed["timeframe_minutes"] = s.timeframe_minutes
    if payload.expiration_minutes:
        s.expiration_minutes = payload.expiration_minutes
        changed["expiration_minutes"] = s.expiration_minutes
    if payload.dry_run is not None:
        s.dry_run = payload.dry_run
        changed["dry_run"] = s.dry_run
    if payload.min_confidence is not None:
        s.strategy.min_confidence = payload.min_confidence
        changed["min_confidence"] = payload.min_confidence

    for field in ("percent_stake", "fixed_stake", "sizing_mode",
                  "max_daily_loss_pct", "max_consecutive_losses",
                  "daily_profit_target_pct"):
        value = getattr(payload, field)
        if value is not None:
            setattr(s.risk, field, value)
            changed[field] = value

    if payload.strategy:
        from ..core.strategies import get_strategy
        try:
            engine.strategy = get_strategy(payload.strategy, s.strategy)
            s.strategy.name = payload.strategy
            engine._last_evaluated_candle = None
            changed["strategy"] = payload.strategy
        except KeyError as exc:
            raise HTTPException(400, detail=str(exc)) from exc

    engine.storage.log_event("INFO", "config", "configuração alterada", changed)
    return {"ok": True, "changed": changed}


# --------------------------------------------------------------------------- #
# Dados
# --------------------------------------------------------------------------- #

@app.get("/api/trades")
async def get_trades(limit: int = 50, engine: TradingEngine = Depends(get_engine)):
    return engine.storage.recent_orders(min(limit, 500))


@app.get("/api/performance")
async def get_performance(engine: TradingEngine = Depends(get_engine)):
    return {
        "daily": engine.storage.daily_summary(30),
        "by_strategy": engine.storage.strategy_performance(),
        "equity_curve": engine.storage.equity_curve(300),
        "stats": engine.risk.stats.to_dict() if engine.risk else None,
    }


@app.get("/api/events")
async def get_events(limit: int = 50, engine: TradingEngine = Depends(get_engine)):
    return engine.storage.recent_events(min(limit, 200))


@app.get("/api/candles")
async def get_candles(limit: int = 200, engine: TradingEngine = Depends(get_engine)):
    """Candles + indicadores, para o gráfico do painel."""
    from ..core import indicators
    try:
        if not engine.broker.is_connected:
            engine.broker.connect()
        df = engine.broker.get_candles(
            engine._active_symbol, engine.settings.timeframe_minutes,
            max(limit, engine.settings.candles_lookback),
        )
        enriched = indicators.enrich(df, engine.settings.strategy).tail(limit)
        enriched = enriched.replace({float("nan"): None})
        return {
            "symbol": engine._active_symbol,
            "timeframe": engine.settings.timeframe_minutes,
            "candles": [
                {
                    "time": row["timestamp"].isoformat(),
                    "open": row["open"], "high": row["high"],
                    "low": row["low"], "close": row["close"],
                    "rsi": row.get("rsi"), "ma_fast": row.get("ma_fast"),
                    "ma_slow": row.get("ma_slow"),
                    "bb_upper": row.get("bb_upper"), "bb_lower": row.get("bb_lower"),
                }
                for _, row in enriched.iterrows()
            ],
        }
    except Exception as exc:
        raise HTTPException(502, detail=f"falha ao obter candles: {exc}") from exc


@app.post("/api/backtest", dependencies=[Depends(require_token)])
async def run_backtest(req: BacktestRequest, engine: TradingEngine = Depends(get_engine)):
    """Roda backtest das estratégias sobre os candles mais recentes."""
    def _work() -> list[dict]:
        if not engine.broker.is_connected:
            engine.broker.connect()
        df = engine.broker.get_candles(
            engine._active_symbol, engine.settings.timeframe_minutes, req.candles
        )
        strat_cfg = engine.settings.strategy.model_copy(
            update={"min_confidence": req.min_confidence}
        )
        bt = Backtester(
            strategy_config=strat_cfg, risk_config=engine.settings.risk,
            payout=req.payout, initial_balance=req.initial_balance,
            expiration_candles=req.expiration_candles,
        )
        names = req.strategies or [s["name"] for s in available_strategies()]
        return bt.compare(df, names, engine._active_symbol)

    try:
        results = await asyncio.to_thread(_work)
    except Exception as exc:
        raise HTTPException(502, detail=f"falha no backtest: {exc}") from exc
    return {
        "symbol": engine._active_symbol,
        "payout": req.payout,
        "breakeven_win_rate": round(100 / (1 + req.payout), 2),
        "results": results,
    }


@app.get("/api/stream")
async def stream(request: Request):
    """Server-Sent Events: status a cada 2s + eventos do engine em tempo real."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_queues.append(queue)

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    msg = {
                        "event": "status",
                        "data": _engine.snapshot() if _engine else {},
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }
                yield f"data: {json.dumps(msg, default=str)}\n\n"
        finally:
            if queue in _event_queues:
                _event_queues.remove(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
