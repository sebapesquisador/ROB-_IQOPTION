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


def _port_livre(host: str, port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1" if host == "0.0.0.0" else host, port))
            return True
        except OSError:
            return False


def cmd_dashboard(args) -> int:
    import uvicorn
    settings = get_settings()
    _banner(settings)
    host = args.host or settings.api_host
    port = args.port or settings.api_port

    # Porta ocupada é comum: outra plataforma, um painel esquecido aberto, etc.
    # O erro cru do uvicorn ("error while attempting to bind") não diz o que
    # fazer, então procuramos a próxima porta livre em vez de abortar.
    if not _port_livre(host, port):
        alternativa = next(
            (p for p in range(port + 1, port + 51) if _port_livre(host, p)), None
        )
        if alternativa is None:
            print(f"\n✖ A porta {port} está ocupada e não há porta livre "
                  f"entre {port + 1} e {port + 50}.")
            print("  Escolha uma manualmente: "
                  "python -m trading_bot.cli dashboard --port 9000\n")
            return 1
        if getattr(args, "port", None):
            # Porta pedida explicitamente: não trocamos por baixo dos panos.
            print(f"\n✖ A porta {port} já está em uso por outro programa.")
            print(f"  Sugestão: --port {alternativa} (está livre)\n")
            return 1
        print(f"\n  ⚠ Porta {port} ocupada por outro programa — usando {alternativa}.")
        print(f"    Para fixar, defina API_PORT={alternativa} no .env")
        port = alternativa

    url_host = "localhost" if host == "0.0.0.0" else host
    print(f"\n  Painel disponível em http://{url_host}:{port}\n")
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
    if getattr(args, "no_otc", False):
        settings.auto_otc = False

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

    if symbol.upper().endswith("-OTC"):
        print()
        print("⚠ ATENÇÃO: este backtest usou um ativo OTC.")
        print("  O preço OTC é gerado pela própria corretora, não vem do mercado")
        print("  interbancário. Resultado obtido em OTC NÃO se transfere para o par")
        print("  real, e vice-versa — são séries de preço diferentes.")
        print("  Para avaliar o par real, rode com o mercado aberto")
        print("  (seg-sex, ~04h-18h de Brasília).")
    print()

    strat_cfg = settings.strategy.model_copy(update={"min_confidence": args.min_confidence})
    bt = Backtester(
        strategy_config=strat_cfg, risk_config=settings.risk,
        payout=args.payout, initial_balance=args.balance,
        expiration_candles=args.expiration_candles,
    )
    names = [args.strategy] if args.strategy else [s["name"] for s in available_strategies()]

    if getattr(args, "holdout", False):
        return _run_holdout(bt, df, names, symbol, args)

    results = bt.compare(df, names, symbol)

    breakeven = 100 / (1 + args.payout)
    print("=" * 105)
    print(f"  BACKTEST — payout {args.payout:.0%} | acerto de equilíbrio: {breakeven:.2f}%")
    print("=" * 105)
    print(f"  {'estratégia':<22}{'trades':>7}{'acerto':>9}{'vantagem':>10}"
          f"{'lucro':>11}{'PF':>7}{'DD%':>7}{'p-valor':>9}")
    print("-" * 105)
    for r in results:
        if "error" in r:
            print(f"  {r['strategy']:<22}  erro: {r['error']}")
            continue
        pf = r["profit_factor"]
        print(f"  {r['strategy']:<22}{r['total_trades']:>7}{r['win_rate']:>8.1f}%"
              f"{r['edge_pp']:>+9.1f}p{r['net_profit']:>+11.2f}"
              f"{(pf if pf is not None else 99.99):>7.2f}{r['max_drawdown_pct']:>7.1f}"
              f"{r.get('p_value', 1.0):>9.3f}")
    print("=" * 105)
    for r in results:
        if "error" not in r:
            print(f"  {r['strategy']:<22} {r['verdict']}")
    print("=" * 105)
    print("\n  p-valor = chance de a vantagem ser sorte. Exigimos <0.010")
    print("  (0.05 corrigido para as 5 estratégias comparadas).")
    print("\n  Lembre-se: resultado passado não garante resultado futuro.")
    print("  Valide em conta demo por semanas antes de considerar dinheiro real.\n")
    return 0


def _run_holdout(bt, df, names, symbol, args) -> int:
    """
    Escolhe a campeã numa fatia dos dados e a testa noutra que ela nunca viu.

    Comparar 5 estratégias e ficar com a melhor infla o resultado mesmo quando
    nenhuma tem vantagem: numa simulação com 5 estratégias de acerto idêntico
    ao ponto de equilíbrio, a "campeã" aparenta +9pp de vantagem só por ruído.
    Escolher e avaliar nos mesmos dados sempre premia a sorte.

    A separação temporal resolve isso: a estratégia é eleita no passado e
    julgada no futuro. Se a vantagem era real, sobrevive; se era ruído do
    período, desaparece — que é justamente o que se quer descobrir antes de
    arriscar dinheiro.
    """
    split = int(len(df) * args.holdout_split)
    treino, teste = df.iloc[:split], df.iloc[split:]

    def periodo(d):
        return (f"{d['timestamp'].iloc[0]:%d/%m %H:%M} → "
                f"{d['timestamp'].iloc[-1]:%d/%m %H:%M}")

    print("=" * 105)
    print("  VALIDAÇÃO FORA DA AMOSTRA (holdout)")
    print("=" * 105)
    print(f"  seleção : {len(treino):>5} candles  ({periodo(treino)})")
    print(f"  teste   : {len(teste):>5} candles  ({periodo(teste)})  ← nunca vistos na seleção")
    print("=" * 105)

    dentro = [r for r in bt.compare(treino, names, symbol) if "error" not in r]
    if not dentro:
        print("\n✖ Nenhuma estratégia produziu resultado na fatia de seleção.\n")
        return 1

    print(f"\n  1) SELEÇÃO — campeã escolhida aqui\n")
    print(f"  {'estratégia':<22}{'trades':>7}{'acerto':>9}{'vantagem':>10}{'lucro':>11}{'p-valor':>9}")
    print("-" * 105)
    for r in sorted(dentro, key=lambda x: -x["net_profit"]):
        print(f"  {r['strategy']:<22}{r['total_trades']:>7}{r['win_rate']:>8.1f}%"
              f"{r['edge_pp']:>+9.1f}p{r['net_profit']:>+11.2f}{r.get('p_value', 1.0):>9.3f}")

    campea = max(dentro, key=lambda r: r["net_profit"])
    nome = campea["strategy"]

    # Campeã sem significância estatística tende a ser a mais sortuda, não a
    # melhor: poucas operações produzem os desvios mais extremos, então a
    # estratégia que menos opera é a que mais aparece no topo por acaso.
    #
    # O critério aqui é o p-valor, não uma contagem fixa de operações: um
    # limiar de "30 trades" deixa passar raspando uma campeã com 31 que já
    # era estatisticamente indistinguível de ruído (p=0,161).
    from .backtest.engine import BacktestResult

    alpha = BacktestResult.ALPHA / BacktestResult.N_COMPARISONS
    if campea.get("p_value", 1.0) > alpha:
        solidas = [r for r in dentro if r.get("p_value", 1.0) <= alpha]
        alternativa = max(solidas, key=lambda r: r["net_profit"]) if solidas else None
        print(f"\n  ⚠ A liderança de {nome} não tem significância estatística "
              f"(p={campea.get('p_value', 1.0):.3f}, exigido <{alpha:.3f}).")
        # A campeã operar bem menos que as rivais é o sinal mais claro de que
        # o topo foi conquistado por variância, não por acerto.
        mediana = sorted(r["total_trades"] for r in dentro)[len(dentro) // 2]
        if mediana and campea["total_trades"] * 2 <= mediana:
            print(f"    Ela opera {mediana / campea['total_trades']:.1f}x menos que a "
                  f"mediana do grupo ({campea['total_trades']} vs {mediana}):")
            print("    amostras pequenas geram os desvios mais extremos, então a")
            print("    estratégia que menos opera é a que mais lidera por sorte.")
        else:
            print(f"    Mesmo com {campea['total_trades']} operações, a diferença para o "
                  "ponto de")
            print("    equilíbrio está dentro do que o acaso produz.")
        if alternativa is not None:
            print(f"    Com significância, a melhor seria {alternativa['strategy']} "
                  f"({alternativa['net_profit']:+.2f}).")
        else:
            print("    Nenhuma das estratégias atingiu significância na seleção —")
            print("    a campeã abaixo é a melhor do grupo, não uma aposta validada.")

    print(f"\n  → campeã na seleção: {nome} "
          f"({campea['win_rate']:.1f}% de acerto, {campea['net_profit']:+.2f})")

    # Avaliamos TODAS fora da amostra, não só a campeã: ver as demais mostra
    # se a liderança se manteve ou se apenas trocou de nome — que é o sintoma
    # clássico de ranking movido a ruído.
    todos_fora = {r["strategy"]: r
                  for r in bt.compare(teste, [r["strategy"] for r in dentro], symbol)
                  if "error" not in r}
    out = todos_fora.get(nome)
    if out is None:
        print(f"\n✖ {nome} não gerou operações no período de teste — "
              "amostra curta demais para validar.\n")
        return 1

    print(f"\n  2) TESTE — desempenho em dados inéditos\n")
    print(f"  {'estratégia':<22}{'trades':>7}{'acerto':>9}{'vantagem':>10}{'lucro':>11}{'p-valor':>9}")
    print("-" * 105)
    for r in sorted(todos_fora.values(), key=lambda x: -x["net_profit"]):
        marca = "  ← campeã da seleção" if r["strategy"] == nome else ""
        print(f"  {r['strategy']:<22}{r['total_trades']:>7}{r['win_rate']:>8.1f}%"
              f"{r['edge_pp']:>+9.1f}p{r['net_profit']:>+11.2f}"
              f"{r.get('p_value', 1.0):>9.3f}{marca}")

    # Agregado das estratégias fora da amostra. Se a perda média por operação
    # converge para a vantagem da casa, a leitura é direta: o conjunto não
    # tem vantagem nenhuma e está apenas pagando o spread do payout.
    n_tot = sum(r["total_trades"] for r in todos_fora.values())
    lucro_tot = sum(r["net_profit"] for r in todos_fora.values())
    positivas = [r for r in todos_fora.values() if r["net_profit"] > 0]
    if n_tot:
        # Expresso em % da aposta para poder comparar com a vantagem da casa.
        # A aposta média sai das derrotas, onde o valor perdido é o stake.
        perdas = sum(r.get("losses", 0) for r in todos_fora.values())
        stake = sum(abs(r.get("gross_loss", 0.0)) for r in todos_fora.values())
        aposta_media = stake / perdas if perdas else 0.0
        esperado_50 = 0.5 * (1 + args.payout) - 1
        print(f"\n  agregado: {len(positivas)} de {len(todos_fora)} positivas | "
              f"{n_tot} operações | {lucro_tot:+.2f}")
        if aposta_media:
            pct = lucro_tot / n_tot / aposta_media
            print(f"  resultado médio por operação: {pct:+.2%} da aposta"
                  f"   (vantagem da casa a 50% de acerto: {esperado_50:+.2%})")

    melhor_fora = max(todos_fora.values(), key=lambda r: r["net_profit"])
    if melhor_fora["strategy"] != nome:
        print(f"\n  ⚠ A melhor no teste foi {melhor_fora['strategy']}, não a campeã.")
        print("    Liderança que troca de dona entre períodos é sinal de ruído,")
        print("    não de vantagem — não adote a nova líder: ela foi escolhida")
        print("    olhando o resultado, o mesmo erro de novo.")

    variacao = out["win_rate"] - campea["win_rate"]
    print("\n" + "=" * 105)
    print(f"  acerto na seleção : {campea['win_rate']:.1f}%")
    print(f"  acerto no teste   : {out['win_rate']:.1f}%   ({variacao:+.1f}pp)")
    print("=" * 105)

    if out["total_trades"] < 30:
        print(f"  INCONCLUSIVO: apenas {out['total_trades']} operações no teste.")
        print("  Rode com mais candles ou timeframe maior.")
    elif out["edge_pp"] <= 0:
        print("  REPROVADA FORA DA AMOSTRA: a vantagem sumiu em dados novos.")
        print("  Era ruído do período de seleção — é assim que backtest bonito")
        print("  vira prejuízo em conta real.")
    elif out.get("p_value", 1.0) > 0.05:
        print("  NÃO COMPROVADA: manteve vantagem, mas sem significância.")
        print("  Sinal encorajador; ainda não é evidência. Amplie a amostra.")
    else:
        print("  SOBREVIVEU: vantagem preservada em dados inéditos.")
        print("  É o resultado mais forte que um backtest pode dar — mesmo assim,")
        print("  valide em DRY_RUN por semanas antes de arriscar dinheiro real.")
    print("=" * 105 + "\n")
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
    p_bt.add_argument("--holdout", action="store_true",
                      help="escolhe a campeã numa fatia dos dados e a testa em "
                           "outra, inédita — separa vantagem real de sorte")
    p_bt.add_argument("--holdout-split", type=float, default=0.7,
                      metavar="FRAC",
                      help="fração dos dados usada para escolher (padrão 0.7)")
    p_bt.add_argument("--no-otc", action="store_true",
                      help="não cair para o par OTC: avalia só o ativo real "
                           "(falha se o mercado estiver fechado)")
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
