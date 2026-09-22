"""
Interface de linha de comando.

Comandos:
  run        executa o robô no terminal
  dashboard  sobe a API + painel web
  backtest   testa estratégias sobre dados históricos
  validate   valida a configuração sem conectar em nada
  strategies lista as estratégias disponíveis
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from .core.config import LOG_DIR, get_settings
from .core.logging_setup import setup_logging

logger = logging.getLogger("trading_bot")


def _banner(settings) -> None:
    live = settings.is_live
    print("=" * 66)
    print("  TRADING BOT v2.0")
    print("=" * 66)
    for k, v in settings.masked().items():
        print(f"  {k:<18} {v}")
    print("=" * 66)
    if live:
        print("  ⚠  MODO REAL — ORDENS COM DINHEIRO DE VERDADE")
        print("=" * 66)


def cmd_run(args) -> int:
    from .brokers import create_broker
    from .core.engine import TradingEngine
    from .core.storage import Storage

    settings = get_settings()
    if args.dry_run:
        settings.dry_run = True
    if args.symbol:
        settings.symbol = args.symbol.upper()
    if args.strategy:
        settings.strategy.name = args.strategy

    _banner(settings)

    if settings.is_live and not args.yes:
        resp = input("\nConfirma operar com DINHEIRO REAL? digite 'CONFIRMO': ")
        if resp.strip() != "CONFIRMO":
            print("Cancelado.")
            return 1

    broker = create_broker(settings)
    engine = TradingEngine(settings, broker, Storage(settings.database_url))

    def shutdown(signum, frame):
        print("\nEncerrando...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if not engine.start():
        logger.error("falha ao iniciar: %s", engine._last_error)
        return 1

    try:
        while True:
            time.sleep(30)
            snap = engine.snapshot()
            r = snap.get("risk") or {}
            st = r.get("stats") or {}
            logger.info(
                "[%s] saldo %.2f | dia %.2f | %d trades | acerto %.1f%%",
                snap["state"], r.get("balance", 0), r.get("daily_pnl", 0),
                st.get("total_trades", 0), st.get("win_rate", 0),
            )
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
    return 0


def cmd_dashboard(args) -> int:
    import uvicorn
    settings = get_settings()
    _banner(settings)
    host = args.host or settings.api_host
    port = args.port or settings.api_port
    print(f"\n  Painel disponível em http://{host}:{port}\n")
    uvicorn.run(
        "trading_bot.api.server:app",
        host=host, port=port, reload=args.reload,
        log_level=settings.log_level.lower(),
    )
    return 0


def cmd_backtest(args) -> int:
    from .backtest import Backtester
    from .brokers import create_broker
    from .core.strategies import available_strategies

    settings = get_settings()
    if args.symbol:
        settings.symbol = args.symbol.upper()

    broker = create_broker(settings)
    if not broker.connect():
        logger.error("falha ao conectar na corretora")
        return 1

    symbol = broker.resolve_symbol(settings.symbol)
    print(f"\nObtendo {args.candles} candles de {symbol}...")
    try:
        df = broker.get_candles(symbol, settings.timeframe_minutes, args.candles)
    except Exception as exc:
        print(f"\n✖ Não foi possível obter os candles.\n  {exc}\n")
        print("  Sugestões:")
        print(f"    • Fora do pregão FOREX, use o par OTC:")
        print(f"        python -m trading_bot.cli backtest --symbol {settings.symbol}-OTC")
        print("    • Confirme o nome do ativo (EURUSD, GBPUSD, EURJPY...)")
        print("    • Teste a estrutura sem corretora com BROKER=paper no .env\n")
        return 1
    finally:
        broker.disconnect()

    if len(df) < 100:
        print(f"\n✖ Apenas {len(df)} candles retornados — insuficiente para backtest.\n")
        return 1

    dias = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds() / 86400
    print(f"Recebidos: {len(df)} candles "
          f"({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}, {dias:.1f} dias)")
    if len(df) < args.candles:
        print(f"⚠ Você pediu {args.candles}, mas só há {len(df)} disponíveis para "
              f"este ativo/timeframe.")
        print("  Para ampliar a amostra, use um timeframe maior "
              "(ex.: --candles 3000 com TIMEFRAME_MINUTES=15 cobre ~1 mês).")
    print()

    strat_cfg = settings.strategy.model_copy(update={"min_confidence": args.min_confidence})
    bt = Backtester(
        strategy_config=strat_cfg, risk_config=settings.risk,
        payout=args.payout, initial_balance=args.balance,
        expiration_candles=args.expiration_candles,
    )
    names = [args.strategy] if args.strategy else [s["name"] for s in available_strategies()]
    results = bt.compare(df, names, settings.symbol)

    breakeven = 100 / (1 + args.payout)
    print("=" * 96)
    print(f"  BACKTEST — payout {args.payout:.0%} | acerto de equilíbrio: {breakeven:.2f}%")
    print("=" * 96)
    print(f"  {'estratégia':<22}{'trades':>7}{'acerto':>9}{'vantagem':>10}"
          f"{'lucro':>11}{'PF':>7}{'DD%':>7}")
    print("-" * 96)
    for r in results:
        if "error" in r:
            print(f"  {r['strategy']:<22}  erro: {r['error']}")
            continue
        pf = r["profit_factor"]
        print(f"  {r['strategy']:<22}{r['total_trades']:>7}{r['win_rate']:>8.1f}%"
              f"{r['edge_pp']:>+9.1f}p{r['net_profit']:>+11.2f}"
              f"{(pf if pf is not None else 99.99):>7.2f}{r['max_drawdown_pct']:>7.1f}")
    print("=" * 96)
    for r in results:
        if "error" not in r:
            print(f"  {r['strategy']:<22} {r['verdict']}")
    print("=" * 96)
    print("\n  Lembre-se: resultado passado não garante resultado futuro.")
    print("  Valide em conta demo por semanas antes de considerar dinheiro real.\n")
    return 0


def cmd_validate(args) -> int:
    try:
        settings = get_settings(reload=True)
    except Exception as exc:
        print(f"✖ Configuração inválida:\n{exc}")
        return 1

    print("✔ Configuração válida\n")
    for k, v in settings.masked().items():
        print(f"  {k:<18} {v}")

    print("\n  Gestão de risco:")
    r = settings.risk
    print(f"    entrada              {r.sizing_mode} "
          f"({r.percent_stake}% / ${r.fixed_stake})")
    print(f"    perda máx. diária    {r.max_daily_loss_pct}%")
    print(f"    drawdown máx.        {r.max_total_drawdown_pct}%")
    print(f"    derrotas seguidas    {r.max_consecutive_losses} → pausa "
          f"{r.cooldown_after_loss_streak_min}min")
    print(f"    meta diária          {r.daily_profit_target_pct}%")
    print(f"    martingale           {'ATIVO ⚠' if r.martingale_enabled else 'desligado ✔'}")

    warnings = []
    if settings.is_live:
        warnings.append("operando em CONTA REAL")
    if r.martingale_enabled:
        warnings.append("martingale ativo — risco de ruína elevado")
    if r.percent_stake > 2:
        warnings.append(f"entrada de {r.percent_stake}% por trade é agressiva")
    if r.max_daily_loss_pct > 10:
        warnings.append(f"perda diária de {r.max_daily_loss_pct}% é alta")

    if warnings:
        print("\n  ⚠ Avisos:")
        for w in warnings:
            print(f"    • {w}")
    print()
    return 0


def cmd_strategies(args) -> int:
    from .core.strategies import available_strategies
    print("\n  Estratégias disponíveis:\n")
    for s in available_strategies():
        print(f"    {s['name']:<22} {s['description']}")
    print()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="trading-bot", description="Robô de trading — IQ Option e Binance"
    )
    parser.add_argument("--log-level", default=None,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="executa o robô")
    p_run.add_argument("--dry-run", action="store_true", help="força modo simulação")
    p_run.add_argument("--symbol", help="sobrescreve o ativo")
    p_run.add_argument("--strategy", help="sobrescreve a estratégia")
    p_run.add_argument("--yes", action="store_true", help="pula a confirmação de conta real")
    p_run.set_defaults(func=cmd_run)

    p_dash = sub.add_parser("dashboard", help="sobe o painel web")
    p_dash.add_argument("--host", default=None)
    p_dash.add_argument("--port", type=int, default=None)
    p_dash.add_argument("--reload", action="store_true")
    p_dash.set_defaults(func=cmd_dashboard)

    p_bt = sub.add_parser("backtest", help="testa estratégias em dados históricos")
    p_bt.add_argument("--strategy", help="testa apenas uma estratégia")
    p_bt.add_argument("--symbol")
    p_bt.add_argument("--candles", type=int, default=1000)
    p_bt.add_argument("--payout", type=float, default=0.85)
    p_bt.add_argument("--balance", type=float, default=1000.0)
    p_bt.add_argument("--min-confidence", type=float, default=0.55)
    p_bt.add_argument("--expiration-candles", type=int, default=1)
    p_bt.set_defaults(func=cmd_backtest)

    sub.add_parser("validate", help="valida a configuração").set_defaults(func=cmd_validate)
    sub.add_parser("strategies", help="lista as estratégias").set_defaults(func=cmd_strategies)

    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        level = args.log_level or settings.log_level
        setup_logging(level, LOG_DIR / "bot.log", settings.log_json)
    except Exception:
        setup_logging(args.log_level or "INFO", LOG_DIR / "bot.log", False)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrompido.")
        return 130
    except Exception as exc:
        logger.exception("erro fatal")
        print(f"\n✖ {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
