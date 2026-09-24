"""
Backtester para mercado spot (Binance).

Por que não reaproveitar o motor de binárias
--------------------------------------------
Opção binária e spot são jogos matematicamente distintos:

| | binária | spot |
|---|---|---|
| saída | no vencimento, hora fixa | quando stop/alvo é tocado |
| perda | 100% da aposta | só a distância até o stop |
| ganho | payout fixo (85%) | distância até o alvo |
| custo | embutido no payout | taxa por ordem (~0,1%) |

Em binárias o acerto precisa vencer o payout: com 85%, 54,05% de acerto
apenas empata. Em spot o acerto sozinho não diz nada — 30% de acerto é
lucrativo se o alvo for 4x o stop. O que decide é a **expectativa**:

    EV = (acerto × ganho_médio) - (erro × perda_média) - custos

Por isso este módulo relata payoff ratio e expectativa por operação, e o
"acerto de equilíbrio" passa a ser derivado da razão alvo/stop, não do
payout.

Premissas conservadoras
-----------------------
* Entrada no OPEN do candle seguinte ao sinal (nunca no close que o gerou).
* Stop e alvo verificados dentro de cada candle, com `low`/`high`.
* Quando um mesmo candle toca stop e alvo, assume-se **stop** — não há como
  saber a ordem dos toques no dado OHLC, e o pessimismo evita inflar o
  resultado.
* Taxa cobrada na entrada e na saída.
* Slippage opcional, aplicado contra a posição nos dois lados.
* Sem posições sobrepostas: uma operação por vez.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from ..core import indicators
from ..core.models import Direction, PerformanceStats
from ..core.strategies import get_strategy

logger = logging.getLogger(__name__)


def payoff_liquido(
    stop_pct: float, target_pct: float,
    fee_pct: float = 0.1, slippage_pct: float = 0.0,
) -> float:
    """Razão ganho/perda depois de taxas e slippage.

    A razão nominal alvo/stop é propaganda: com alvo 2% e stop 1% ela diz
    2,00, mas o custo aparece dos dois lados da conta — encolhe o ganho e
    engorda a perda. A 0,1% por ordem sobram (2,0-0,2)/(1,0+0,2) = 1,50.

    A diferença não é cosmética: muda o acerto de equilíbrio de 33,3% para
    40,0%. Uma estratégia com 38% de acerto parece vencedora pela conta
    nominal e perde dinheiro na real.
    """
    custo = 2 * (fee_pct + slippage_pct)   # entrada e saída
    ganho = target_pct - custo
    perda = stop_pct + custo
    if perda <= 0:
        return 0.0
    return max(ganho, 0.0) / perda


def breakeven_liquido(
    stop_pct: float, target_pct: float,
    fee_pct: float = 0.1, slippage_pct: float = 0.0,
) -> float:
    """Acerto (%) necessário para empatar, já contando os custos."""
    r = payoff_liquido(stop_pct, target_pct, fee_pct, slippage_pct)
    if r <= 0:
        return 100.0
    return 100.0 / (1.0 + r)


@dataclass(slots=True)
class SpotTrade:
    entry_time: Any
    exit_time: Any
    direction: str
    entry_price: float
    exit_price: float
    qty: float
    reason: str          # "alvo", "stop" ou "fim dos dados"
    gross: float
    fees: float
    net: float
    bars_held: int


@dataclass(slots=True)
class SpotResult:
    """Resultado de um backtest spot, pronto para serializar."""

    strategy: str
    symbol: str
    initial_balance: float
    final_balance: float
    stop_loss_pct: float
    take_profit_pct: float
    fee_pct: float
    trades: list[SpotTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    stats: PerformanceStats = field(default_factory=PerformanceStats)
    candles_tested: int = 0

    ALPHA = 0.05
    N_COMPARISONS = 5

    @property
    def payoff_ratio(self) -> float:
        """Ganho médio dividido pela perda média. Em spot, importa mais que o acerto."""
        wins = [t.net for t in self.trades if t.net > 0]
        losses = [abs(t.net) for t in self.trades if t.net < 0]
        if not wins or not losses:
            return 0.0
        return (sum(wins) / len(wins)) / (sum(losses) / len(losses))

    @property
    def breakeven_win_rate(self) -> float:
        """
        Acerto necessário para empatar, dado o payoff observado.

        Com payoff R, o equilíbrio é 1/(1+R): alvo igual ao stop exige 50%;
        alvo com o dobro do stop exige 33,3%.
        """
        r = self.payoff_ratio
        return 100.0 / (1.0 + r) if r > 0 else 100.0

    @property
    def edge(self) -> float:
        return self.stats.win_rate - self.breakeven_win_rate

    @property
    def expectancy_pct(self) -> float:
        """Resultado médio por operação, em % do saldo inicial."""
        if not self.trades:
            return 0.0
        return (self.stats.net_profit / len(self.trades)) / self.initial_balance * 100

    @property
    def total_fees(self) -> float:
        return sum(t.fees for t in self.trades)

    @property
    def p_value(self) -> float:
        """
        Teste binomial contra o acerto de equilíbrio implícito no payoff.

        Mesmo critério do motor binário: sem isto, uma sequência de sorte em
        poucas operações vira "estratégia lucrativa".
        """
        n = self.stats.wins + self.stats.losses
        if n == 0:
            return 1.0
        k = self.stats.wins
        p = self.breakeven_win_rate / 100.0
        if k <= 0 or not 0.0 < p < 1.0:
            return 1.0
        log_p, log_q = math.log(p), math.log1p(-p)
        total = 0.0
        for i in range(k, n + 1):
            total += math.exp(
                math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                + i * log_p + (n - i) * log_q
            )
        return min(1.0, total)

    def _verdict(self) -> str:
        if self.stats.total_trades < 30:
            return "amostra insuficiente — não confie neste resultado"
        if self.stats.net_profit <= 0:
            return "REPROVADA: perde dinheiro depois das taxas"
        alpha = self.ALPHA / self.N_COMPARISONS
        if self.p_value > alpha:
            return (f"NÃO COMPROVADA: lucro pode ser sorte "
                    f"(p={self.p_value:.3f}, exigido <{alpha:.3f})")
        if self.stats.max_drawdown_pct > 30:
            return "ARRISCADA: lucrativa, mas com drawdown alto demais"
        return "APROVADA: lucro consistente, estatisticamente significativo"

    def to_dict(self) -> dict[str, Any]:
        ret = ((self.final_balance - self.initial_balance) / self.initial_balance * 100
               if self.initial_balance else 0.0)
        return {
            "summary": {
                "strategy": self.strategy,
                "symbol": self.symbol,
                "candles_tested": self.candles_tested,
                "initial_balance": round(self.initial_balance, 2),
                "final_balance": round(self.final_balance, 2),
                "return_pct": round(ret, 2),
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
                "fee_pct": self.fee_pct,
                "payoff_ratio": round(self.payoff_ratio, 2),
                "breakeven_win_rate": round(self.breakeven_win_rate, 2),
                "edge_pp": round(self.edge, 2),
                "expectancy_pct": round(self.expectancy_pct, 4),
                "total_fees": round(self.total_fees, 2),
                "p_value": round(self.p_value, 4),
                "verdict": self._verdict(),
                **self.stats.to_dict(),
            },
            "equity_curve": [round(v, 2) for v in self.equity_curve],
            "trades": [
                {
                    "entry_time": str(t.entry_time), "exit_time": str(t.exit_time),
                    "direction": t.direction, "entry_price": t.entry_price,
                    "exit_price": t.exit_price, "reason": t.reason,
                    "net": round(t.net, 4), "fees": round(t.fees, 4),
                    "bars_held": t.bars_held,
                }
                for t in self.trades
            ],
        }


@dataclass(slots=True)
class _Preparado:
    """Candles enriquecidos e sinais já calculados, prontos para reuso."""
    data: pd.DataFrame
    sinais: list          # índice do candle -> True (long), False (short) ou None
    warmup: int
    strategy_name: str


class _EntradaAleatoria:
    """Entra em candles sorteados, sem olhar para o preço.

    Deliberadamente burra: é o controle do experimento. Qualquer
    estratégia que não supere isto não está extraindo informação do
    mercado, apenas pagando taxa para sortear.
    """

    __slots__ = ("prob", "_rng", "_warmup")

    def __init__(self, prob: float, seed: int, warmup: int = 50) -> None:
        self.prob = prob
        self._rng = random.Random(seed)
        self._warmup = warmup

    def required_candles(self) -> int:
        return self._warmup

    def evaluate(self, window):
        acionavel = self._rng.random() < self.prob
        return _SinalSimples(Direction.CALL, acionavel)


@dataclass(slots=True)
class _SinalSimples:
    direction: Any
    is_actionable: bool


class SpotBacktester:
    """
    Simula compra e venda a mercado com stop e alvo.

    Diferente do motor de binárias, aqui a saída depende do caminho do preço
    dentro dos candles, não de um vencimento fixo.
    """

    def __init__(
        self,
        strategy_config,
        risk_config=None,
        *,
        stop_loss_pct: float = 1.0,
        take_profit_pct: float = 1.5,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.0,
        initial_balance: float = 1000.0,
        allow_short: bool = False,
        max_bars: int = 0,
    ) -> None:
        self.strategy_config = strategy_config
        self.risk_cfg = risk_config
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.initial_balance = initial_balance
        # Spot comum não permite vender o que não se tem; short exige margem.
        self.allow_short = allow_short
        # Trava de tempo: evita capital preso indefinidamente numa posição.
        self.max_bars = max_bars

    def preparar(self, candles: pd.DataFrame, strategy_name: str,
                 strategy=None) -> "_Preparado":
        """Enriquece os candles e calcula os sinais uma única vez.

        Os sinais de uma estratégia não dependem de stop nem de alvo — só
        do preço e dos indicadores. Varrer dez combinações de barreiras
        recalculando tudo dez vezes custaria dez vezes mais por nada.

        Diferença sutil em relação ao `run` direto: aqui a estratégia é
        consultada em todos os candles, inclusive nos que ela passaria em
        branco por haver posição aberta. Para estratégias determinísticas
        (todas as reais) o resultado é idêntico; para a referência
        aleatória mudaria a sequência sorteada, por isso ela não usa este
        caminho.
        """
        if strategy is None:
            strategy = get_strategy(strategy_name, self.strategy_config)
        data = indicators.enrich(candles, self.strategy_config).reset_index(drop=True)
        warmup = strategy.required_candles()

        sinais: list[Optional[bool]] = [None] * len(data)
        for i in range(warmup, max(warmup, len(data) - 2)):
            sig = strategy.evaluate(data.iloc[: i + 1])
            if sig.is_actionable:
                sinais[i] = sig.direction is Direction.CALL
        return _Preparado(data=data, sinais=sinais, warmup=warmup,
                          strategy_name=strategy_name)

    def run(self, candles: pd.DataFrame, strategy_name: str,
            symbol: str = "BTCUSDT", strategy=None,
            preparado: "Optional[_Preparado]" = None) -> SpotResult:
        # `strategy` injetável para poder rodar a referência aleatória, que
        # não está (nem deve estar) no registro de estratégias reais.
        # `preparado` reaproveita sinais já calculados (varredura de barreiras).
        if preparado is not None:
            strategy, data = None, preparado.data
            strategy_name = strategy_name or preparado.strategy_name
        else:
            if strategy is None:
                strategy = get_strategy(strategy_name, self.strategy_config)
            data = indicators.enrich(candles, self.strategy_config).reset_index(drop=True)

        result = SpotResult(
            strategy=strategy_name, symbol=symbol,
            initial_balance=self.initial_balance, final_balance=self.initial_balance,
            stop_loss_pct=self.stop_loss_pct, take_profit_pct=self.take_profit_pct,
            fee_pct=self.fee_pct, candles_tested=len(data),
        )

        warmup = preparado.warmup if preparado is not None else strategy.required_candles()
        if len(data) <= warmup + 3:
            logger.warning("candles insuficientes para %s", strategy_name)
            return result

        balance = self.initial_balance
        peak = balance
        result.equity_curve.append(balance)

        stake_pct = getattr(self.risk_cfg, "percent_stake", 1.0) if self.risk_cfg else 1.0
        fixed_stake = getattr(self.risk_cfg, "fixed_stake", 10.0) if self.risk_cfg else 10.0
        sizing = getattr(self.risk_cfg, "sizing_mode", "percent") if self.risk_cfg else "percent"

        fee = self.fee_pct / 100.0
        slip = self.slippage_pct / 100.0
        i = warmup

        while i < len(data) - 2:
            if preparado is not None:
                marca = preparado.sinais[i]
                if marca is None:
                    i += 1
                    continue
                is_long = marca
            else:
                signal = strategy.evaluate(data.iloc[: i + 1])
                if not signal.is_actionable:
                    i += 1
                    continue
                is_long = signal.direction is Direction.CALL
            if not is_long and not self.allow_short:
                i += 1
                continue

            entry_idx = i + 1
            if entry_idx >= len(data):
                break

            # Slippage sempre contra a posição
            raw_entry = float(data["open"].iloc[entry_idx])
            entry = raw_entry * (1 + slip) if is_long else raw_entry * (1 - slip)
            if entry <= 0:
                i += 1
                continue

            notional = fixed_stake if sizing == "fixed" else balance * (stake_pct / 100.0)
            notional = min(notional, balance)
            if notional <= 0:
                break
            qty = notional / entry

            if is_long:
                stop = entry * (1 - self.stop_loss_pct / 100.0)
                target = entry * (1 + self.take_profit_pct / 100.0)
            else:
                stop = entry * (1 + self.stop_loss_pct / 100.0)
                target = entry * (1 - self.take_profit_pct / 100.0)

            exit_idx, exit_price, reason = None, None, ""
            limite = (entry_idx + self.max_bars) if self.max_bars else len(data) - 1

            for j in range(entry_idx, min(limite, len(data) - 1) + 1):
                hi = float(data["high"].iloc[j])
                lo = float(data["low"].iloc[j])

                if is_long:
                    bateu_stop, bateu_alvo = lo <= stop, hi >= target
                else:
                    bateu_stop, bateu_alvo = hi >= stop, lo <= target

                # Ambos no mesmo candle: o OHLC não revela a ordem dos toques.
                # Assumir stop é a escolha pessimista — o oposto infla o retorno.
                if bateu_stop:
                    exit_idx, exit_price, reason = j, stop, "stop"
                    break
                if bateu_alvo:
                    exit_idx, exit_price, reason = j, target, "alvo"
                    break

            if exit_idx is None:
                exit_idx = min(limite, len(data) - 1)
                exit_price = float(data["close"].iloc[exit_idx])
                reason = "tempo" if self.max_bars else "fim dos dados"

            exit_price = exit_price * (1 - slip) if is_long else exit_price * (1 + slip)

            gross = (exit_price - entry) * qty if is_long else (entry - exit_price) * qty
            fees = (entry * qty * fee) + (exit_price * qty * fee)
            net = gross - fees

            balance += net
            result.stats.total_trades += 1
            result.stats.net_profit += net
            if net > 0:
                result.stats.wins += 1
                result.stats.gross_profit += net
                result.stats.current_streak = max(1, result.stats.current_streak + 1)
                result.stats.max_win_streak = max(
                    result.stats.max_win_streak, result.stats.current_streak)
            elif net < 0:
                result.stats.losses += 1
                result.stats.gross_loss += net
                result.stats.current_streak = min(-1, result.stats.current_streak - 1)
                result.stats.max_loss_streak = max(
                    result.stats.max_loss_streak, abs(result.stats.current_streak))
            else:
                result.stats.ties += 1

            result.trades.append(SpotTrade(
                entry_time=data["timestamp"].iloc[entry_idx],
                exit_time=data["timestamp"].iloc[exit_idx],
                direction="LONG" if is_long else "SHORT",
                entry_price=round(entry, 8), exit_price=round(exit_price, 8),
                qty=qty, reason=reason, gross=gross, fees=fees, net=net,
                bars_held=exit_idx - entry_idx,
            ))

            result.equity_curve.append(balance)
            peak = max(peak, balance)
            dd = peak - balance
            if dd > result.stats.max_drawdown:
                result.stats.max_drawdown = dd
                result.stats.max_drawdown_pct = (dd / peak * 100) if peak else 0.0

            if balance <= 0:
                logger.warning("backtest interrompido: saldo zerado")
                break

            # Sem posições sobrepostas: retoma no candle seguinte à saída
            i = exit_idx + 1

        result.stats.equity_peak = peak
        result.final_balance = balance
        return result

    def compare(self, candles: pd.DataFrame, names: list[str],
                symbol: str = "BTCUSDT") -> list[dict]:
        saida = []
        for nome in names:
            try:
                saida.append(self.run(candles, nome, symbol).to_dict()["summary"])
            except Exception as exc:  # pragma: no cover - proteção de borda
                logger.error("falha ao testar %s: %s", nome, exc)
                saida.append({"strategy": nome, "error": str(exc)})
        return sorted(saida, key=lambda r: r.get("net_profit", float("-inf")), reverse=True)

    def preparar_aleatorio(self, data: pd.DataFrame, prob: float,
                           seed: int, warmup: int = 50) -> "_Preparado":
        """Sinais sorteados sobre candles já enriquecidos.

        Usado na varredura: fixar os pontos de entrada entre as
        combinações de barreiras isola o efeito do stop e do alvo. Se as
        entradas mudassem junto, não daria para saber o que causou o quê.
        """
        rng = random.Random(seed)
        sinais: list[Optional[bool]] = [None] * len(data)
        for i in range(warmup, max(warmup, len(data) - 2)):
            if rng.random() < prob:
                sinais[i] = True
        return _Preparado(data=data, sinais=sinais, warmup=warmup,
                          strategy_name="aleatório")

    def densidade_de_sinais(self, preparado: "_Preparado") -> float:
        """Fração de candles em que a estratégia quer entrar."""
        marcas = sum(1 for m in preparado.sinais if m is not None)
        return marcas / max(len(preparado.sinais), 1)

    def referencia_aleatoria(
        self, candles: pd.DataFrame, n_trades_alvo: int,
        symbol: str = "BTCUSDT", seeds: int = 7,
    ) -> dict:
        """Mede o que entradas sorteadas produzem nos mesmos candles.

        É a pergunta que o relatório não respondia: uma estratégia com 33%
        de acerto é ruim, ou é isso que qualquer entrada produz com estas
        barreiras? Com stop 1% e alvo 2%, um passeio aleatório toca o stop
        duas vezes mais que o alvo — o acerto esperado é 1/3, sem que
        nenhuma informação sobre o mercado esteja envolvida.

        Sem essa linha, 33% parece um defeito das estratégias. Com ela,
        fica claro que é o piso da mecânica, e que o trabalho da estratégia
        é ficar acima dele.

        Roda várias sementes porque uma só teria o mesmo problema de
        amostra que estamos tentando diagnosticar. Devolve média e extremos
        — os extremos são a faixa de ruído.
        """
        if len(candles) < 60 or n_trades_alvo <= 0:
            return {}

        prob = min(1.0, n_trades_alvo / max(len(candles) - 50, 1))
        linhas = []
        for seed in range(seeds):
            r = self.run(candles, "aleatório", symbol,
                         strategy=_EntradaAleatoria(prob, seed))
            if r.stats.total_trades:
                linhas.append(r.to_dict()["summary"])
        if not linhas:
            return {}

        def media(campo):
            return sum(l[campo] for l in linhas) / len(linhas)

        acertos = sorted(l["win_rate"] for l in linhas)
        return {
            "strategy": f"aleatório ({len(linhas)} sementes)",
            "total_trades": round(media("total_trades")),
            "win_rate": round(media("win_rate"), 1),
            "payoff_ratio": round(media("payoff_ratio"), 2),
            "net_profit": round(media("net_profit"), 2),
            "total_fees": round(media("total_fees"), 2),
            "max_drawdown_pct": round(media("max_drawdown_pct"), 1),
            "win_rate_min": round(acertos[0], 1),
            "win_rate_max": round(acertos[-1], 1),
            "sementes": len(linhas),
        }
