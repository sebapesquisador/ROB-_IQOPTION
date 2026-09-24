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

from .core.config import LOG_DIR, checar_simbolo, get_settings
from .core.logging_setup import setup_logging

logger = logging.getLogger("trading_bot")


# Símbolos que o relatório usa e que faltam em codificações antigas como a
# cp1252 do Windows. Cada um tem um equivalente que cabe em qualquer lugar.
_SUBSTITUTOS = {
    "→": "->", "←": "<-", "⟶": "->",
    "✔": "OK", "✖": "x", "⚠": "!", "✓": "ok", "✗": "x",
    "≈": "~", "≤": "<=", "≥": ">=", "≠": "!=",
    "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
    "█": "#", "░": ".", "•": "*", "…": "...",
}


def _codificacao_do_console() -> "str | None":
    """Página de código que o console do Windows usa para LER a saída.

    O detalhe que a primeira correção errou: quando a saída é
    redirecionada, o Python escolhe a codificação ANSI do sistema (cp1252),
    mas o PowerShell decodifica os bytes com a página de código do console,
    que é OEM (cp850 no Brasil). As duas diferem justamente nos acentos, e
    "estratégia" chega como "estratÚgia".

    Escrever em UTF-8 não resolveria: o PowerShell continuaria lendo como
    cp850. A única saída que casa é escrever na codificação que ele lê.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        cp = int(ctypes.windll.kernel32.GetConsoleOutputCP())
    except Exception:
        return None
    if cp <= 0:
        return None
    if cp == 65001:
        return "utf-8"
    codec = f"cp{cp}"
    try:
        "teste".encode(codec)
    except LookupError:
        return None
    return codec


def _ajustar_saida_para_o_terminal() -> None:
    """Impede que um símbolo derrube o programa em terminais antigos.

    No Windows, o Python escreve UTF-8 no console mas usa a codificação
    local (cp1252) quando a saída é redirecionada — `| Tee-Object`, `>
    arquivo.txt`, um pipe qualquer. Aí uma seta comum derruba tudo com
    UnicodeEncodeError, e o tratador de erro derruba de novo ao tentar
    imprimir o próprio aviso de falha.

    Duas correções, nesta ordem:

    1. Escrever na codificação que o console REALMENTE lê (ver
       _codificacao_do_console). Sem isso não há travamento, mas os acentos
       chegam trocados.
    2. Trocar os símbolos que não existem nessa codificação. Os acentos
       cabem em cp850 e cp1252; a seta e o "✔" não.

    Forçar UTF-8 seria a correção intuitiva e estaria errada: o PowerShell
    decodifica com a página de código do console de qualquer jeito, e todo
    o texto em português viraria ruído.
    """
    console = _codificacao_do_console()
    for stream in (sys.stdout, sys.stderr):
        # Só interfere quando a saída é redirecionada: no console de verdade
        # o Python já conversa em Unicode com o Windows e está tudo certo.
        redirecionada = not getattr(stream, "isatty", lambda: False)()
        if console and redirecionada:
            try:
                stream.reconfigure(encoding=console, errors="replace")
            except Exception:
                pass

        codificacao = getattr(stream, "encoding", None) or "utf-8"
        try:
            "".join(_SUBSTITUTOS).encode(codificacao)
            continue          # o terminal dá conta de tudo
        except (UnicodeEncodeError, LookupError):
            pass

        faltantes = {}
        for simbolo, alternativa in _SUBSTITUTOS.items():
            try:
                simbolo.encode(codificacao)
            except (UnicodeEncodeError, LookupError):
                faltantes[ord(simbolo)] = alternativa
        try:
            stream.reconfigure(errors="replace")   # rede de segurança
        except Exception:
            pass
        if faltantes:
            _instalar_traducao(stream, faltantes)


def _instalar_traducao(stream, tabela: dict) -> None:
    """Troca os símbolos ausentes na hora de escrever."""
    original = stream.write

    def write(texto, _orig=original, _tab=tabela):
        return _orig(texto.translate(_tab) if isinstance(texto, str) else texto)

    try:
        stream.write = write          # type: ignore[method-assign]
    except (AttributeError, TypeError):
        pass


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
    if getattr(args, "timeframe", None):
        settings.timeframe_minutes = args.timeframe

    broker = create_broker(settings)
    if not broker.connect():
        logger.error("falha ao conectar na corretora")
        return 1

    symbol = broker.resolve_symbol(settings.symbol)
    tf = settings.timeframe_minutes
    cobertura = args.candles * tf / 60 / 24
    print(f"\nObtendo {args.candles} candles de {symbol} "
          f"em {tf} min (~{cobertura:.1f} dias de pregão)...")
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
        return _run_holdout(bt, df, names, symbol, args, settings.timeframe_minutes)

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


def _run_holdout(bt, df, names, symbol, args, settings_tf: int | None = None) -> int:
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
        import math as _math

        print(f"  INCONCLUSIVO: apenas {out['total_trades']} operações no teste.")
        # Com amostra assim, o desvio padrão do acerto é enorme: informar a
        # faixa que o puro acaso cobre evita que o número seja lido como sinal.
        n = out["total_trades"]
        if n:
            be = 1.0 / (1.0 + args.payout)
            sd = _math.sqrt(be * (1 - be) / n) * 100
            print(f"  Com {n} operações, o acaso sozinho cobre de "
                  f"{max(0.0, be * 100 - 2 * sd):.0f}% a {min(100.0, be * 100 + 2 * sd):.0f}% "
                  f"de acerto — o resultado acima não distingue sorte de vantagem.")
            # Quantos candles seriam necessários para 30 operações no teste.
            candles_teste = len(teste)
            por_candle = n / candles_teste if candles_teste else 0
            if por_candle > 0:
                need_total = int(_math.ceil((30 / por_candle) / (1 - args.holdout_split)))
                print(f"  Para 30 operações no teste seriam ~{need_total} candles "
                      f"(agora: {len(df)}).")
                # Aumentar o timeframe NÃO ajuda aqui: cobre mais tempo, mas a
                # fatia de teste continua com o mesmo número de candles, e os
                # sinais nascem de candles. O que aumenta operações é mais
                # candles ou uma fatia de teste maior.
                if need_total > 5000:
                    novo_split = max(0.3, round(1 - (30 / por_candle) / len(df), 2))
                    print("  A corretora dificilmente entrega tantos candles. "
                          "Alternativa: destinar")
                    print("  mais dados ao teste (a seleção fica menor, mas o "
                          "veredito é o que importa):")
                    print(f"  python -m trading_bot.cli backtest --candles "
                          f"{args.candles} --holdout --holdout-split {novo_split}")
                    print("  Observação: aumentar --timeframe cobre mais tempo, "
                          "mas não gera mais")
                    print("  operações — a fatia de teste continua com o mesmo "
                          "número de candles.")
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


def _diagnostico_env() -> None:
    """
    Mostra de onde cada valor está vindo.

    Editar o .env e o robô seguir usando o valor antigo é uma das falhas mais
    difíceis de perceber: nada dá erro, o número simplesmente não muda. As
    causas comuns são silenciosas — arquivo salvo como `.env.txt` pela
    extensão oculta do Windows, execução a partir de outra pasta, ou uma
    variável de ambiente que tem precedência sobre o arquivo.
    """
    import os

    cwd = Path.cwd()
    env = cwd / ".env"

    print("  Arquivo de configuração:")
    if env.is_file():
        print(f"    ✔ {env}")
    else:
        print(f"    ✖ NÃO existe: {env}")
        parecidos = sorted(
            p.name for p in cwd.glob(".env*")
            if p.is_file() and p.name not in (".env", ".env.example")
        )
        if parecidos:
            print(f"      encontrados na pasta: {', '.join(parecidos)}")
            if ".env.txt" in parecidos:
                print("      → o Windows esconde a extensão .txt; renomeie para .env")
        outros = sorted(p / ".env" for p in cwd.parents if (p / ".env").is_file())
        if outros:
            print(f"      existe um .env em: {outros[0]}")
            print("      → rode o comando de dentro dessa pasta")

    # Variáveis de ambiente têm precedência sobre o arquivo e mascaram a edição
    observadas = ["TIMEFRAME_MINUTES", "EXPIRATION_MINUTES", "BROKER",
                  "DRY_RUN", "SYMBOL", "ACCOUNT_MODE"]
    do_ambiente = {k: os.environ[k] for k in observadas if k in os.environ}
    if do_ambiente:
        print("\n  ⚠ Definidas no ambiente (têm prioridade sobre o .env):")
        for k, v in do_ambiente.items():
            print(f"    {k}={v}")
        print("    → enquanto existirem, editar o .env não muda nada.")
        print("    → para limpar nesta sessão do PowerShell:")
        for k in do_ambiente:
            print(f"       Remove-Item Env:\\{k}")
    print()


def cmd_backtest_spot(args) -> int:
    """
    Backtest para mercado spot (Binance).

    Separado de `backtest` porque a mecânica é outra: em spot a saída ocorre
    quando stop ou alvo é tocado, o prejuízo é a distância até o stop (não a
    aposta inteira) e o custo é a taxa por ordem. Relatar spot com a
    matemática de binárias produziria números sem sentido.
    """
    from .backtest import SpotBacktester
    from .brokers import create_broker
    from .core.strategies import available_strategies

    settings = get_settings()
    if args.symbol:
        settings.symbol = args.symbol.upper()
    if getattr(args, "timeframe", None):
        settings.timeframe_minutes = args.timeframe

    # Antes de conectar: conectar leva segundos e o erro só apareceria
    # depois, parecendo problema de rede em vez de ativo errado.
    problema = checar_simbolo(settings.broker, settings.symbol)
    if problema:
        print(f"\n✖ {problema}\n")
        print("  Corrija SYMBOL no .env ou passe --symbol BTCUSDT nesta linha.\n")
        return 1

    broker = create_broker(settings)
    if not broker.connect():
        logger.error("falha ao conectar na corretora")
        print("\n✖ Não foi possível conectar.")
        print("  Para testar sem corretora: BROKER=paper no .env\n")
        return 1

    symbol = settings.symbol
    tf = settings.timeframe_minutes
    print(f"\nObtendo {args.candles} candles de {symbol} em {tf} min...")
    try:
        df = broker.get_candles(symbol, tf, args.candles)
    except Exception as exc:
        print(f"\n✖ Não foi possível obter candles: {exc}\n")
        return 1
    finally:
        broker.disconnect()

    if len(df) < 100:
        print(f"\n✖ Apenas {len(df)} candles — insuficiente.\n")
        return 1

    dias = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds() / 86400
    print(f"Recebidos: {len(df)} candles "
          f"({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}, {dias:.1f} dias)\n")

    bt = SpotBacktester(
        settings.strategy.model_copy(update={"min_confidence": args.min_confidence}),
        settings.risk,
        stop_loss_pct=args.stop, take_profit_pct=args.target,
        fee_pct=args.fee, slippage_pct=args.slippage,
        initial_balance=args.balance, max_bars=args.max_bars,
    )
    names = [args.strategy] if args.strategy else [s["name"] for s in available_strategies()]
    if args.sweep:
        return _varredura_barreiras(bt, df, names, symbol, args)

    results = bt.compare(df, names, symbol)

    from .backtest.spot import (breakeven_liquido, comprar_e_segurar,
                                payoff_liquido)

    rr = args.target / args.stop if args.stop else 0
    be_bruto = 100 / (1 + rr) if rr else 0
    # O que vale é o número depois do custo. A razão nominal alvo/stop
    # superestima o payoff e faz uma estratégia perdedora parecer vencedora.
    rr_liq = payoff_liquido(args.stop, args.target, args.fee, args.slippage)
    be_liq = breakeven_liquido(args.stop, args.target, args.fee, args.slippage)

    print("=" * 105)
    print(f"  BACKTEST SPOT — stop {args.stop}% | alvo {args.target}% | "
          f"taxa {args.fee}% por ordem")
    print(f"  payoff líquido {rr_liq:.2f}x → ACERTO DE EQUILÍBRIO {be_liq:.1f}%"
          f"   (nominal {rr:.2f}x / {be_bruto:.1f}% antes do custo)")
    print("=" * 105)
    print(f"  {'estratégia':<22}{'trades':>7}{'acerto':>9}{'payoff':>8}"
          f"{'lucro':>11}{'taxas':>9}{'DD%':>7}{'p-valor':>9}")
    print("-" * 105)
    for r in results:
        if "error" in r:
            print(f"  {r['strategy']:<22}  erro: {r['error']}")
            continue
        print(f"  {r['strategy']:<22}{r['total_trades']:>7}{r['win_rate']:>8.1f}%"
              f"{r['payoff_ratio']:>8.2f}{r['net_profit']:>+11.2f}"
              f"{r['total_fees']:>9.2f}{r['max_drawdown_pct']:>7.1f}"
              f"{r.get('p_value', 1.0):>9.3f}")

    # Referência aleatória: sem ela, um acerto de 33% parece defeito da
    # estratégia quando pode ser só a mecânica das barreiras.
    base = {}
    if not args.no_baseline:
        validos_bt = [r for r in results if "error" not in r and r["total_trades"]]
        if validos_bt:
            alvo = round(sum(r["total_trades"] for r in validos_bt) / len(validos_bt))
            base = bt.referencia_aleatoria(df, alvo, symbol)
    if base:
        print("-" * 105)
        print(f"  {base['strategy']:<22}{base['total_trades']:>7}"
              f"{base['win_rate']:>8.1f}%{base['payoff_ratio']:>8.2f}"
              f"{base['net_profit']:>+11.2f}{base['total_fees']:>9.2f}"
              f"{base['max_drawdown_pct']:>7.1f}"
              f"{'—':>9}")
        faixa = f"{base['win_rate_min']:.1f}% a {base['win_rate_max']:.1f}%"
        print(f"  {'':<22}   acerto das sementes: {faixa}  ← qualquer "
              f"estratégia dentro desta faixa não se distingue de sorteio")

    print("=" * 105)
    for r in results:
        if "error" not in r:
            print(f"  {r['strategy']:<22} {r['verdict']}")
    print("=" * 105)
    print(f"\n  payoff = ganho médio ÷ perda média. Em spot o acerto sozinho não")
    print(f"  decide: com estes parâmetros, o alvo é passar de {be_liq:.1f}%.")

    if base:
        melhor = max((r for r in results if "error" not in r and r["total_trades"]),
                     key=lambda r: r["win_rate"], default=None)
        if melhor:
            dif = melhor["win_rate"] - base["win_rate"]
            print(f"\n  Leitura da referência aleatória:")
            print(f"    entradas sorteadas acertam {base['win_rate']:.1f}% — é o piso "
                  f"que a mecânica\n    de stop {args.stop}% / alvo {args.target}% "
                  f"produz sem informação nenhuma.")
            dentro = base["win_rate_min"] <= melhor["win_rate"] <= base["win_rate_max"]
            if dentro:
                print(f"    A melhor estratégia ({melhor['strategy']}, "
                      f"{melhor['win_rate']:.1f}%) cai DENTRO da faixa de\n"
                      f"    ruído: nestes dados ela não prevê nada que o acaso "
                      f"não preveja.")
            elif dif > 0:
                # Ficar acima da faixa de 7 sementes NÃO é significância:
                # a faixa depende do número de sementes, não do tamanho da
                # amostra. Sem este teste o relatório anunciava "há sinal"
                # para um resultado com p de 0,17.
                from .backtest.spot import p_binomial_cauda
                n_m = melhor["total_trades"]
                vitorias = round(melhor["win_rate"] * n_m / 100)
                pv = p_binomial_cauda(vitorias, n_m, base["win_rate"] / 100)
                falta_be = melhor["win_rate"] - be_liq
                print(f"    {melhor['strategy']} fica {dif:+.1f}pp acima do sorteio, "
                      f"em {n_m} operações.")
                if pv < 0.05:
                    print(f"    Isso é mais do que o acaso costuma produzir "
                          f"(p={pv:.3f}), mas ainda\n    {falta_be:+.1f}pp do "
                          f"equilíbrio de {be_liq:.1f}% — sinal pequeno demais "
                          f"para pagar o custo.")
                else:
                    preciso = _trades_para_significancia(
                        melhor["win_rate"] / 100, base["win_rate"] / 100)
                    print(f"    Mas p={pv:.3f}: está dentro do que o acaso produz "
                          f"nessa amostra.")
                    if preciso:
                        print(f"    Seriam necessárias ~{preciso} operações para "
                              f"essa diferença\n    significar alguma coisa "
                              f"(tem {n_m}).")
            else:
                print(f"    {melhor['strategy']} fica {dif:+.1f}pp ABAIXO do sorteio: "
                      f"as regras estão\n    piorando a entrada, não melhorando.")
            print(f"\n    Compare sempre contra esta linha, não contra zero.")

    # Amostra: 30 operações é o mínimo para o teste ter alguma força. Com
    # dados da Binance isso é resolvível — o histórico tem anos, e o único
    # custo de pedir mais candles é esperar alguns segundos a mais.
    validos = [r for r in results if "error" not in r]
    magros = [r for r in validos if r["total_trades"] < 30]
    if magros and validos:
        pior = min(validos, key=lambda r: r["total_trades"])
        por_candle = pior["total_trades"] / len(df) if len(df) else 0
        if por_candle > 0:
            preciso = int(40 / por_candle / 1000 + 1) * 1000
            dias = preciso * tf / 60 / 24
            print(f"\n  ⚠ {len(magros)} de {len(validos)} estratégias ficaram abaixo "
                  f"de 30 operações — amostra pequena demais para concluir")
            print(f"    qualquer coisa. A Binance entrega anos de histórico; "
                  f"peça mais candles:")
            print(f"\n    python -m trading_bot.cli backtest-spot --symbol {symbol} "
                  f"--candles {preciso} \\")
            print(f"        --stop {args.stop} --target {args.target}")
            print(f"\n    ({preciso} candles de {tf} min ≈ {dias:.0f} dias; "
                  f"a busca é paginada, leva alguns segundos)")

    # Benchmark que nenhuma estratégia só comprada pode ignorar.
    bh = comprar_e_segurar(df, args.fee)
    print(f"\n  Comprar e segurar no período: {bh:+.1f}%")
    if bh > 5:
        print(f"    O {symbol} subiu. Estratégia só comprada herda parte dessa alta,")
        print(f"    então acerto alto aqui não é mérito da regra — é do mercado.")
    elif bh < -5:
        print(f"    O {symbol} caiu. Num mercado assim, perder pouco parece bom —")
        print(f"    mas veja a exposição antes de comemorar: ficar de fora numa")
        print(f"    queda não é mérito da estratégia, é ausência dela.")
    else:
        print(f"    Mercado de lado no período: o benchmark não atrapalha nem ajuda.")
    exposicoes = [(r["strategy"], r.get("exposicao_pct", 0.0))
                  for r in results if "error" not in r]
    if exposicoes:
        media_exp = sum(e for _, e in exposicoes) / len(exposicoes)
        print(f"    Exposição média das estratégias: {media_exp:.0f}% do tempo "
              f"com posição aberta,")
        print(f"    arriscando ~1% do saldo por vez. Comprar e segurar fica "
              f"100% do tempo")
        print(f"    exposto com 100% do capital — por isso os valores em dólar não")
        print(f"    se comparam. O que se compara é a existência de vantagem.")

    print("\n  Valide em conta demo por semanas antes de considerar dinheiro real.\n")
    return 0


def _trades_para_significancia(taxa: float, nulo: float,
                               alpha: float = 0.05, teto: int = 50000):
    """Quantas operações essa diferença precisaria para convencer.

    Transforma "não deu" em algo acionável: ou o usuário consegue essa
    amostra, ou a diferença é pequena demais para ser perseguida.
    """
    from .backtest.spot import p_binomial_cauda
    if taxa <= nulo:
        return None
    for n in range(50, teto, 50):
        if p_binomial_cauda(round(taxa * n), n, nulo) < alpha:
            return n
    return None


def _varredura_barreiras(bt, df, names, symbol, args) -> int:
    """Testa combinações de stop e alvo contra entradas sorteadas.

    Fecha a objeção que sobra depois de um resultado ruim: "e se o problema
    forem só os parâmetros?". Se a estratégia carrega informação, ela vence
    o sorteio em alguma configuração.

    Duas colunas são o coração da tabela e foram acrescentadas depois de a
    primeira versão enganar:

    * `falta` — distância até o equilíbrio líquido. Ganhar do sorteio não
      paga conta; o que paga é passar do equilíbrio. Uma estratégia pode
      ter sinal real e ainda assim perder dinheiro, se o sinal for menor
      que o custo.
    * `p` — chance de o acaso produzir aquela diferença, dado o número de
      operações. Sem ela, +9,4pp em 80 operações parece mais forte que
      +2,5pp em 500, quando é o contrário.

    Os sinais são calculados uma vez por estratégia e reaproveitados em
    todas as barreiras: a única coisa que muda entre as linhas é o stop e
    o alvo.
    """
    from .backtest.spot import breakeven_liquido, p_binomial_cauda

    grade = [
        (0.5, 0.5), (0.5, 1.0), (0.5, 1.5),
        (1.0, 1.0), (1.0, 2.0), (1.0, 3.0),
        (2.0, 2.0), (2.0, 4.0), (2.0, 6.0),
        # Barreiras largas: a taxa é um custo fixo em %, então quanto maior
        # o movimento buscado, menos ela pesa. Se houver sinal, é aqui que
        # ele tem a melhor chance de sobrar depois do custo.
        (3.0, 3.0), (3.0, 9.0), (4.0, 12.0),
    ]
    SEEDS = 5
    MIN_TRADES_CONFIAVEL = 100

    print(f"\nCalculando sinais de {len(names)} estratégias "
          f"(uma vez só, reaproveitados em {len(grade)} combinações)...")
    preps = {}
    for nome in names:
        try:
            preps[nome] = bt.preparar(df, nome)
        except Exception as exc:
            logger.error("falha ao preparar %s: %s", nome, exc)
    if not preps:
        print("\n✖ Nenhuma estratégia pôde ser preparada.\n")
        return 1

    dados = next(iter(preps.values())).data
    densidade = sum(bt.densidade_de_sinais(pp) for pp in preps.values()) / len(preps)
    aleatorios = [bt.preparar_aleatorio(dados, densidade, seed) for seed in range(SEEDS)]

    # Toda comparação feita conta para a correção de multiplicidade.
    comparacoes = len(grade) * len(preps)
    alpha = 0.05 / comparacoes

    print("\n" + "=" * 112)
    print(f"  VARREDURA DE BARREIRAS — {symbol}, {len(df)} candles, "
          f"taxa {args.fee}% por ordem")
    print(f"  {comparacoes} comparações → exigimos p < {alpha:.4f} "
          f"(0,05 corrigido por Bonferroni)")
    print("=" * 112)
    print(f"  {'stop':>5}{'alvo':>6}{'equil.':>9}   {'melhor estratégia':<21}"
          f"{'n':>6}{'acerto':>8}{'sorteio':>9}{'ganha do':>10}{'falta':>9}"
          f"{'p':>9}")
    print(f"  {'':>5}{'':>6}{'':>9}   {'':<21}{'':>6}{'':>8}{'':>9}"
          f"{'sorteio':>10}{'p/ lucro':>9}{'':>9}")
    print("-" * 112)

    diferencas, faltas, achados = [], [], []
    for stop, alvo in grade:
        bt.stop_loss_pct, bt.take_profit_pct = stop, alvo
        be = breakeven_liquido(stop, alvo, args.fee, args.slippage)

        linhas = []
        for nome, prep in preps.items():
            r = bt.run(df, nome, symbol, preparado=prep)
            if r.stats.total_trades >= 20:
                linhas.append((nome, r.stats.win_rate, r.stats.net_profit,
                               r.stats.total_trades, r.stats.wins))
        acertos = []
        for prep_a in aleatorios:
            ra = bt.run(df, "aleatório", symbol, preparado=prep_a)
            if ra.stats.total_trades:
                acertos.append(ra.stats.win_rate)
        if not linhas or not acertos:
            print(f"  {stop:>5.1f}{alvo:>6.1f}{be:>8.1f}%   "
                  f"(operações de menos para comparar)")
            continue

        # Melhor contra melhor: a coluna da estratégia é o máximo de N, o
        # sorteio também. Confrontar o melhor de N com a média do acaso
        # fabrica vantagem — foi como a fase da IQ Option produziu +9pp.
        sorteio = max(acertos)
        # Para o p-valor, a hipótese nula é o comportamento TÍPICO do acaso.
        nulo = sum(acertos) / len(acertos) / 100.0

        nome, acerto, lucro, n, wins = max(linhas, key=lambda l: l[1])
        dif = acerto - sorteio
        falta = acerto - be
        pv = p_binomial_cauda(wins, n, nulo)
        diferencas.append(dif)
        # Só entra na leitura final quem tem amostra para significar algo.
        if n >= MIN_TRADES_CONFIAVEL:
            faltas.append((falta, n, stop, alvo))
        if pv < alpha and falta > 0:
            achados.append((stop, alvo, nome, falta, pv))

        # A marca exige os DOIS critérios. Marcar só por `falta` positiva
        # destacaria linhas de 30 operações com p de 0,5 — foi o que a
        # primeira versão fez, apontando ruído como se fosse achado.
        marca = "  <<" if (falta > 0 and pv < alpha) else ""
        print(f"  {stop:>5.1f}{alvo:>6.1f}{be:>8.1f}%   {nome:<21}{n:>6}"
              f"{acerto:>7.1f}%{sorteio:>8.1f}%{dif:>+9.1f}pp{falta:>+8.1f}pp"
              f"{pv:>9.3f}{marca}")

    print("=" * 112)
    if diferencas:
        media = sum(diferencas) / len(diferencas)
        print(f"\n  Ganha do sorteio, em média: {media:+.1f}pp — "
              f"mas o que paga conta é a coluna 'falta'.")
        if faltas:
            melhor_falta, n_melhor, s_melhor, a_melhor = max(faltas)
            print(f"  Melhor distância até o lucro, entre as linhas com pelo "
                  f"menos {MIN_TRADES_CONFIAVEL}\n  operações: "
                  f"{melhor_falta:+.1f}pp (stop {s_melhor}% / alvo {a_melhor}%, "
                  f"{n_melhor} operações).")
        else:
            melhor_falta = -99.0
            print(f"  Nenhuma linha chegou a {MIN_TRADES_CONFIAVEL} operações: "
                  f"não há o que concluir de\n  nenhuma delas, por melhor que "
                  f"a coluna 'falta' pareça.")

        if achados:
            print("\n  Combinações que passaram nos dois critérios "
                  "(lucrativas E significativas):")
            for stop, alvo, nome, falta, pv in achados:
                print(f"    stop {stop}% / alvo {alvo}% — {nome} "
                      f"({falta:+.1f}pp, p={pv:.4f})")
            print("\n  Antes de acreditar: rode a combinação isolada com "
                  "--holdout. Escolher a\n  melhor entre muitas premia a "
                  "sorte, e a correção de Bonferroni não\n  desfaz isso "
                  "completamente.")
        elif melhor_falta > -2.0:
            print("\n  Nenhuma combinação fecha no azul, mas a melhor chegou perto,")
            print("  e com amostra suficiente para não ser só ruído. A coluna")
            print("  'falta' encolhe conforme as barreiras aumentam: a taxa é um")
            print("  custo fixo em %, então quanto maior o movimento buscado, menos")
            print("  ela pesa. Vale testar uma taxa menor (--fee 0.075, desconto")
            print("  BNB) antes de desistir.")
        else:
            print("\n  Nenhuma combinação chega ao equilíbrio. O stop e o alvo")
            print("  decidem QUANTAS operações ganham, não SE há o que ganhar.")
            print("  Barreiras mais largas reduzem o peso da taxa, mas também")
            print("  reduzem o número de operações: o que parece melhora costuma")
            print("  ser só a amostra encolhendo.")
    print(f"\n  << marca as linhas lucrativas E significativas (falta > 0 e "
          f"p < {alpha:.4f}).\n  Uma coisa sem a outra não vale: no ruído puro "
          f"aparecem linhas com\n  'falta' de +8pp e p de 0,3.\n")
    return 0


def cmd_funding(args) -> int:
    """Testa se o funding rate prevê o retorno seguinte do spot.

    Primeiro teste do projeto com um dado que NÃO é o preço. As cinco
    estratégias anteriores liam só a cotação e todas empataram com sorteio,
    o que era previsível: indicador calculado sobre o preço é função do que
    todo mundo já vê. O funding é um pagamento real entre participantes, e
    mede posicionamento — pode não prever nada, mas ao menos não é
    tautológico.
    """
    from .backtest.funding_signal import (alinhar, dividir, por_quantil,
                                          teste_permutacao)
    from .brokers import create_broker
    from .data.funding import baixar_funding, rendimento_carry

    settings = get_settings()
    symbol = (args.symbol or settings.symbol).upper()
    tf = args.timeframe or settings.timeframe_minutes

    print(f"\nBaixando {args.periodos} pagamentos de funding de {symbol}...")
    try:
        funding = baixar_funding(symbol, args.periodos)
    except Exception as exc:
        print(f"\n✖ {exc}\n")
        return 1
    dias = len(funding) * 8 / 24
    print(f"Recebidos: {len(funding)} pagamentos "
          f"({funding['timestamp'].iloc[0]:%Y-%m-%d} → "
          f"{funding['timestamp'].iloc[-1]:%Y-%m-%d}, {dias:.0f} dias)")

    # Candles suficientes para cobrir o mesmo período, com folga.
    candles_necessarios = int(dias * 24 * 60 / tf) + 200
    print(f"Baixando {candles_necessarios} candles de {tf} min...")
    broker = create_broker(settings)
    if not broker.connect():
        print("\n✖ Não foi possível conectar para obter os candles.\n")
        return 1
    try:
        candles = broker.get_candles(symbol, tf, candles_necessarios)
    except Exception as exc:
        print(f"\n✖ Não foi possível obter candles: {exc}\n")
        return 1
    finally:
        broker.disconnect()

    dados = alinhar(funding, candles, args.horizonte)
    if len(dados) < 40:
        print(f"\n✖ Só {len(dados)} eventos puderam ser alinhados — "
              f"insuficiente.\n")
        return 1

    # ---------------- carrego: aritmética, não previsão ----------------
    carry = rendimento_carry(funding)
    print("\n" + "=" * 92)
    print(f"  FUNDING DE {symbol} — {carry['periodos']} pagamentos, "
          f"{carry['dias']:.0f} dias")
    print("=" * 92)
    print(f"  média por período (8h)    {carry['media_por_periodo_pct']:+.5f}%")
    print(f"  acumulado no período      {carry['acumulado_pct']:+.2f}%")
    print(f"  equivalente anual         {carry['anualizado_pct']:+.2f}%")
    print(f"  períodos positivos        {carry['positivos_pct']:.1f}%")
    print(f"  extremos                  {carry['menor_pct']:+.4f}% a "
          f"{carry['maior_pct']:+.4f}%")
    print("\n  Isto NÃO é previsão: é uma taxa observada. Quem vende o perpétuo")
    print("  e compra o spot na mesma quantidade fica neutro em preço e recebe")
    print("  esse valor. Os riscos ficam fora desta conta (liquidação, execução,")
    print("  corretora) — mas a taxa em si não depende de acertar direção.")

    # ---------------- sinal: precisa passar no teste ----------------
    print("\n" + "=" * 92)
    print(f"  O FUNDING PREVÊ O RETORNO DAS PRÓXIMAS {args.horizonte}h?")
    print(f"  {len(dados)} eventos alinhados | entrada no candle seguinte ao "
          f"pagamento")
    print("=" * 92)
    print(f"  {'grupo':>6}{'n':>7}{'funding médio':>16}{'retorno médio':>16}"
          f"{'subiu':>9}")
    print("-" * 92)
    for g in por_quantil(dados, args.grupos):
        print(f"  {g['grupo']:>6}{g['n']:>7}{g['funding_medio_pct']:>15.5f}%"
              f"{g['retorno_medio_pct']:>15.4f}%{g['acerto_alta_pct']:>8.1f}%")
    print("-" * 92)

    treino, teste = dividir(dados, args.holdout_split)
    r_treino = teste_permutacao(treino, args.grupos, args.permutacoes, seed=1)
    r_teste = teste_permutacao(teste, args.grupos, args.permutacoes, seed=2)

    if not r_treino or not r_teste:
        print("\n  Amostra insuficiente para separar treino e teste.\n")
        return 1

    print(f"\n  Spread = retorno do grupo de funding MAIS BAIXO menos o do "
          f"MAIS ALTO.")
    print(f"  A hipótese contrária prevê spread positivo.\n")
    print(f"  {'fatia':<10}{'eventos':>9}{'spread':>11}{'p-valor':>10}")
    print(f"  {'treino':<10}{r_treino['n']:>9}{r_treino['spread_pct']:>+10.4f}%"
          f"{r_treino['p_value']:>10.4f}")
    print(f"  {'teste':<10}{r_teste['n']:>9}{r_teste['spread_pct']:>+10.4f}%"
          f"{r_teste['p_value']:>10.4f}   ← nunca usado para escolher nada")

    print("\n" + "=" * 92)
    if r_teste["p_value"] < 0.05 and r_teste["spread_pct"] > 0:
        print("  SOBREVIVEU AO TESTE FORA DA AMOSTRA")
        print(f"  Spread de {r_teste['spread_pct']:+.4f}% com p={r_teste['p_value']:.4f}.")
        print("  Próximo passo: verificar se o tamanho paga o custo. Um spread")
        print("  menor que 0,2% (ida e volta na taxa) não vira lucro.")
    elif r_treino["p_value"] < 0.05:
        print("  NÃO CONFIRMADO FORA DA AMOSTRA")
        print(f"  Apareceu no treino (p={r_treino['p_value']:.4f}) e sumiu no "
              f"teste (p={r_teste['p_value']:.4f}).")
        print("  É o padrão de quem encontrou uma coincidência, não um efeito.")
    else:
        print("  SEM EFEITO DETECTÁVEL")
        print(f"  Nem no treino (p={r_treino['p_value']:.4f}) nem no teste "
              f"(p={r_teste['p_value']:.4f}).")
        print("  O funding não antecipa o retorno deste horizonte.")
    print("=" * 92)

    if args.horizonte > 8:
        print(f"\n  ⚠ Horizonte de {args.horizonte}h é maior que o intervalo "
              f"entre pagamentos (8h):")
        print(f"    janelas consecutivas se sobrepõem e as observações não são")
        print(f"    independentes. O teste de permutação sofre menos com isso que")
        print(f"    um teste clássico, mas o p-valor ainda fica otimista.")

    print(f"\n  Repare na diferença entre as duas metades do relatório: o")
    print(f"  carrego é uma taxa que existe independentemente de previsão; o")
    print(f"  sinal precisa passar num teste. Só a segunda parte pode falhar.\n")
    return 0


def cmd_validate(args) -> int:
    try:
        settings = get_settings(reload=True)
    except Exception as exc:
        print(f"✖ Configuração inválida:\n{exc}")
        return 1

    print("✔ Configuração válida\n")
    _diagnostico_env()
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
    problema = checar_simbolo(settings.broker, settings.symbol)
    if problema:
        warnings.append(problema)
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


def build_parser() -> argparse.ArgumentParser:
    """Constrói o parser. Separado de main() para poder ser testado."""
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
    p_bt.add_argument("--timeframe", type=int, metavar="MIN",
                      help="minutos por candle (padrão: TIMEFRAME_MINUTES do .env). "
                           "Timeframe maior cobre mais tempo com os mesmos candles")
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

    p_spot = sub.add_parser("backtest-spot",
                            help="testa estratégias em mercado spot (Binance)")
    p_spot.add_argument("--strategy", help="testa apenas uma estratégia")
    p_spot.add_argument("--symbol")
    p_spot.add_argument("--candles", type=int, default=1000)
    p_spot.add_argument("--timeframe", type=int, metavar="MIN")
    p_spot.add_argument("--stop", type=float, default=1.0,
                        help="stop loss em %% do preço de entrada (padrão 1.0)")
    p_spot.add_argument("--target", type=float, default=1.5,
                        help="alvo em %% do preço de entrada (padrão 1.5)")
    p_spot.add_argument("--sweep", action="store_true",
                        help="varre combinações de stop/alvo contra o sorteio")
    p_spot.add_argument("--no-baseline", action="store_true",
                        help="não calcular a referência de entradas aleatórias")
    p_spot.add_argument("--fee", type=float, default=0.1,
                        help="taxa por ordem em %% (padrão 0.1 = Binance spot)")
    p_spot.add_argument("--slippage", type=float, default=0.0,
                        help="deslizamento em %% aplicado contra a posição")
    p_spot.add_argument("--max-bars", type=int, default=0,
                        help="fecha a posição após N candles (0 = sem limite)")
    p_spot.add_argument("--balance", type=float, default=1000.0)
    p_spot.add_argument("--min-confidence", type=float, default=0.55)
    p_spot.set_defaults(func=cmd_backtest_spot)

    p_fund = sub.add_parser(
        "funding", help="testa se o funding rate prevê o retorno do spot")
    p_fund.add_argument("--symbol", help="par de perpétuo, ex.: BTCUSDT")
    p_fund.add_argument("--periodos", type=int, default=1000,
                        help="pagamentos de funding (8h cada; 1000 ≈ 333 dias)")
    p_fund.add_argument("--horizonte", type=int, default=8,
                        help="horas de retorno medidas após cada pagamento")
    p_fund.add_argument("--timeframe", type=int, default=None)
    p_fund.add_argument("--grupos", type=int, default=5,
                        help="quantis de funding (5 = quintis)")
    p_fund.add_argument("--permutacoes", type=int, default=5000)
    p_fund.add_argument("--holdout-split", type=float, default=0.3,
                        help="fração final reservada para teste")
    p_fund.set_defaults(func=cmd_funding)

    sub.add_parser("validate", help="valida a configuração").set_defaults(func=cmd_validate)
    sub.add_parser("strategies", help="lista as estratégias").set_defaults(func=cmd_strategies)

    return parser


def main(argv=None) -> int:
    # Antes de qualquer print: um símbolo não pode derrubar o programa.
    _ajustar_saida_para_o_terminal()
    parser = build_parser()
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
        try:
            print(f"\n✖ {exc}")
        except UnicodeEncodeError:
            # Último recurso: o aviso de erro jamais pode ser o erro.
            sys.stdout.write("\nERRO: " + str(exc).encode(
                "ascii", "replace").decode("ascii") + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
