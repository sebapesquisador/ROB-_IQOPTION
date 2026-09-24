"""
Backtester de mercado spot.

Spot e opção binária são jogos distintos: em spot a saída ocorre quando
stop ou alvo é tocado, o prejuízo é a distância até o stop (não a aposta
inteira) e o custo é a taxa por ordem — cerca de 0,2% ida e volta, contra
os 7,5% embutidos no payout de 85% de uma binária.
"""
import pandas as pd
import pytest

from trading_bot.core.config import StrategyConfig
from trading_bot.core.models import Direction
import trading_bot.backtest.spot as spot_mod
from trading_bot.backtest.spot import SpotBacktester, SpotResult


T0 = pd.Timestamp("2026-01-01", tz="UTC")


def candles(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "timestamp", [T0 + pd.Timedelta(minutes=5 * i) for i in range(len(df))])
    df["volume"] = 1.0
    return df


@pytest.fixture
def sinal_no_candle_5(monkeypatch):
    """Estratégia determinística: dispara LONG uma única vez, no índice 5."""
    class Fake:
        def __init__(self, direction=Direction.CALL, quando=5):
            self.direction, self.quando = direction, quando

        def required_candles(self):
            return 3

        def evaluate(self, window):
            d, q = self.direction, self.quando

            class S:
                direction = d
                is_actionable = (len(window) - 1 == q)
            return S()

    holder = {"strategy": Fake()}
    monkeypatch.setattr(spot_mod, "get_strategy", lambda n, c: holder["strategy"])
    monkeypatch.setattr(spot_mod.indicators, "enrich", lambda df, cfg: df)
    return holder


class TestMecanica:
    """A aritmética precisa bater com a conta feita à mão."""

    def _base(self):
        return [(100, 100.1, 99.9, 100)] * 6 + [(100, 100.2, 99.9, 100)]

    def test_alvo_batido_calcula_liquido_exato(self, sinal_no_candle_5):
        rows = self._base() + [(100, 102.0, 99.6, 101), (101, 101.2, 100.8, 101)]
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.5,
                            fee_pct=0.1, initial_balance=1000.0)
        r = bt.run(candles(rows), "x")
        t = r.trades[0]
        qty = 10.0 / 100.0                       # 1% de 1000, entrada a 100
        bruto = (101.5 - 100) * qty
        taxas = (100 * qty * 0.001) + (101.5 * qty * 0.001)
        assert t.reason == "alvo"
        assert t.net == pytest.approx(bruto - taxas, abs=1e-9)

    def test_stop_batido_limita_a_perda(self, sinal_no_candle_5):
        rows = self._base() + [(100, 100.2, 98.0, 99), (99, 99.2, 98.8, 99)]
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.5,
                            fee_pct=0.1, initial_balance=1000.0)
        r = bt.run(candles(rows), "x")
        t = r.trades[0]
        assert t.reason == "stop"
        assert t.exit_price == pytest.approx(99.0)
        # Perde só a distância até o stop, não o notional inteiro
        assert -0.15 < t.net < 0

    def test_stop_e_alvo_no_mesmo_candle_assume_stop(self, sinal_no_candle_5):
        """OHLC não revela a ordem dos toques; o pessimismo evita inflar."""
        rows = self._base() + [(100, 102.0, 98.0, 99), (99, 99.2, 98.8, 99)]
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.5)
        t = bt.run(candles(rows), "x").trades[0]
        assert t.reason == "stop"

    def test_taxa_cobrada_nos_dois_lados(self, sinal_no_candle_5):
        rows = self._base() + [(100, 102.0, 99.6, 101), (101, 101.2, 100.8, 101)]
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.5,
                            fee_pct=0.1, initial_balance=1000.0)
        t = bt.run(candles(rows), "x").trades[0]
        qty = 10.0 / 100.0
        assert t.fees == pytest.approx((100 * qty + 101.5 * qty) * 0.001, abs=1e-9)

    def test_taxa_zero_preserva_o_bruto(self, sinal_no_candle_5):
        rows = self._base() + [(100, 102.0, 99.6, 101), (101, 101.2, 100.8, 101)]
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.5,
                            fee_pct=0.0)
        t = bt.run(candles(rows), "x").trades[0]
        assert t.fees == 0.0
        assert t.net == pytest.approx(t.gross)

    def test_slippage_atua_contra_a_posicao(self, sinal_no_candle_5):
        rows = self._base() + [(100, 102.0, 99.6, 101), (101, 101.2, 100.8, 101)]
        limpo = SpotBacktester(None, None, take_profit_pct=1.5, fee_pct=0.0)
        sujo = SpotBacktester(None, None, take_profit_pct=1.5, fee_pct=0.0,
                              slippage_pct=0.05)
        a = limpo.run(candles(rows), "x").trades[0]
        b = sujo.run(candles(rows), "x").trades[0]
        assert b.entry_price > a.entry_price     # compra mais caro
        assert b.net < a.net

    def test_short_bloqueado_por_padrao(self, sinal_no_candle_5):
        sinal_no_candle_5["strategy"].direction = Direction.PUT
        rows = self._base() + [(100, 100.2, 98.0, 99), (99, 99.2, 98.8, 99)]
        bt = SpotBacktester(None, None)
        assert bt.run(candles(rows), "x").trades == []

    def test_short_lucra_na_queda_quando_habilitado(self, sinal_no_candle_5):
        sinal_no_candle_5["strategy"].direction = Direction.PUT
        rows = self._base() + [(100, 100.2, 97.0, 98), (98, 98.2, 97.8, 98)]
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.5,
                            fee_pct=0.0, allow_short=True)
        t = bt.run(candles(rows), "x").trades[0]
        assert t.direction == "SHORT"
        assert t.reason == "alvo"
        assert t.net > 0

    def test_max_bars_fecha_por_tempo(self, sinal_no_candle_5):
        """Sem stop nem alvo tocados, a posição não fica presa para sempre."""
        rows = self._base() + [(100, 100.1, 99.95, 100)] * 10
        bt = SpotBacktester(None, None, stop_loss_pct=5.0, take_profit_pct=5.0,
                            fee_pct=0.0, max_bars=3)
        t = bt.run(candles(rows), "x").trades[0]
        assert t.reason == "tempo"
        assert t.bars_held <= 3


class TestMetricas:
    def _res(self, wins, losses, ganho=2.0, perda=1.0):
        r = SpotResult(strategy="t", symbol="BTCUSDT", initial_balance=1000.0,
                       final_balance=1000.0, stop_loss_pct=1.0,
                       take_profit_pct=2.0, fee_pct=0.1)
        from trading_bot.backtest.spot import SpotTrade
        for _ in range(wins):
            r.trades.append(SpotTrade(0, 0, "LONG", 1, 1, 1, "alvo", ganho, 0, ganho, 1))
        for _ in range(losses):
            r.trades.append(SpotTrade(0, 0, "LONG", 1, 1, 1, "stop", -perda, 0, -perda, 1))
        r.stats.wins, r.stats.losses = wins, losses
        r.stats.total_trades = wins + losses
        r.stats.net_profit = wins * ganho - losses * perda
        return r

    def test_payoff_ratio(self):
        assert self._res(10, 10, ganho=2.0, perda=1.0).payoff_ratio == pytest.approx(2.0)

    def test_breakeven_cai_com_payoff_alto(self):
        """Payoff 2.0 exige apenas 33,3% de acerto — o oposto de uma binária."""
        assert self._res(10, 10, 2.0, 1.0).breakeven_win_rate == pytest.approx(33.33, abs=0.1)
        assert self._res(10, 10, 1.0, 1.0).breakeven_win_rate == pytest.approx(50.0)
        assert self._res(10, 10, 3.0, 1.0).breakeven_win_rate == pytest.approx(25.0)

    def test_acerto_baixo_com_payoff_alto_e_lucrativo(self):
        """4 vitórias em 10 com payoff 3.0 dá lucro — impossível em binária."""
        r = self._res(4, 6, ganho=3.0, perda=1.0)
        assert r.stats.net_profit > 0
        assert r.edge > 0

    def test_verdict_reprova_prejuizo(self):
        r = self._res(10, 40, ganho=1.0, perda=1.0)
        assert "REPROVADA" in r._verdict()

    def test_verdict_exige_amostra(self):
        assert "insuficiente" in self._res(5, 5)._verdict()

    def test_verdict_exige_significancia(self):
        r = self._res(20, 20, ganho=1.2, perda=1.0)
        assert "NÃO COMPROVADA" in r._verdict() or "APROVADA" in r._verdict()

    def test_p_value_entre_zero_e_um(self):
        assert 0.0 <= self._res(40, 60, 2.0, 1.0).p_value <= 1.0

    def test_dict_expoe_campos_de_spot(self):
        d = self._res(20, 20)._res if False else self._res(20, 20).to_dict()["summary"]
        for campo in ("payoff_ratio", "total_fees", "expectancy_pct",
                      "stop_loss_pct", "take_profit_pct", "p_value"):
            assert campo in d


class TestSemPosicoesSobrepostas:
    def test_nao_abre_nova_antes_de_fechar(self, monkeypatch):
        """Uma operação por vez: o capital não é alocado duas vezes."""
        class Sempre:
            def required_candles(self):
                return 3

            def evaluate(self, window):
                class S:
                    direction = Direction.CALL
                    is_actionable = True
                return S()

        monkeypatch.setattr(spot_mod, "get_strategy", lambda n, c: Sempre())
        monkeypatch.setattr(spot_mod.indicators, "enrich", lambda df, cfg: df)

        rows = [(100, 100.5, 99.5, 100)] * 40
        bt = SpotBacktester(None, None, stop_loss_pct=1.0, take_profit_pct=1.0,
                            fee_pct=0.0, max_bars=2)
        r = bt.run(candles(rows), "x")
        for a, b in zip(r.trades, r.trades[1:]):
            assert a.exit_time < b.entry_time


class TestCustoNoEquilibrio:
    """O custo muda o acerto necessário, e o relatório precisa dizer isso.

    Com alvo 2%, stop 1% e taxa 0,1%, a razão nominal é 2,00 e sugere
    equilíbrio em 33,3%. O número real é 1,50 e 40,0% — a diferença decide
    se uma estratégia de 38% de acerto é aprovada ou reprovada.
    """

    def test_payoff_liquido_do_caso_2x1(self):
        from trading_bot.backtest.spot import payoff_liquido
        # (2.0 - 0.2) / (1.0 + 0.2)
        assert payoff_liquido(1.0, 2.0, fee_pct=0.1) == pytest.approx(1.5)

    def test_breakeven_liquido_do_caso_2x1(self):
        from trading_bot.backtest.spot import breakeven_liquido
        assert breakeven_liquido(1.0, 2.0, fee_pct=0.1) == pytest.approx(40.0)

    def test_sem_custo_volta_ao_nominal(self):
        from trading_bot.backtest.spot import breakeven_liquido, payoff_liquido
        assert payoff_liquido(1.0, 2.0, fee_pct=0.0) == pytest.approx(2.0)
        assert breakeven_liquido(1.0, 2.0, fee_pct=0.0) == pytest.approx(100 / 3)

    def test_slippage_soma_ao_custo(self):
        from trading_bot.backtest.spot import payoff_liquido
        # fee 0.1 + slip 0.05 = 0.15 por lado → 0.3 ida e volta
        assert payoff_liquido(1.0, 2.0, 0.1, 0.05) == pytest.approx(1.7 / 1.3)

    def test_custo_maior_que_o_alvo_zera_o_payoff(self):
        from trading_bot.backtest.spot import breakeven_liquido, payoff_liquido
        # Alvo de 0.1% com taxa de 0.1% por ordem: impossível ganhar.
        assert payoff_liquido(1.0, 0.1, fee_pct=0.1) == 0.0
        assert breakeven_liquido(1.0, 0.1, fee_pct=0.1) == 100.0

    def test_alvo_apertado_exige_acerto_alto(self):
        from trading_bot.backtest.spot import breakeven_liquido
        # Scalp de 0.3% com stop 0.3%: o custo domina.
        be = breakeven_liquido(0.3, 0.3, fee_pct=0.1)
        assert be > 50.0          # nominal diria exatamente 50%
        assert be == pytest.approx(100 * 0.5 / (0.5 + 0.1), rel=1e-6)

    def test_bate_com_o_que_o_motor_realmente_entrega(self, sinal_no_candle_5):
        """O número do cabeçalho tem de casar com a aritmética do motor.

        Roda um trade que bate no alvo e outro que bate no stop, com os
        mesmos parâmetros, e confere que ganho/perda é o payoff anunciado.
        """
        from trading_bot.backtest.spot import payoff_liquido

        base = [(100, 100.1, 99.9, 100)] * 6 + [(100, 100.2, 99.9, 100)]
        kw = dict(stop_loss_pct=1.0, take_profit_pct=2.0, fee_pct=0.1,
                  initial_balance=1000.0)

        ganho_rows = base + [(100, 103.0, 99.6, 102), (102, 102.2, 101.8, 102)]
        g = SpotBacktester(None, None, **kw).run(candles(ganho_rows), "x")
        assert g.trades[0].reason == "alvo"

        perda_rows = base + [(100, 100.2, 98.0, 99), (99, 99.2, 98.8, 99)]
        pr = SpotBacktester(None, None, **kw).run(candles(perda_rows), "x")
        assert pr.trades[0].reason == "stop"

        observado = g.trades[0].net / abs(pr.trades[0].net)
        assert observado == pytest.approx(payoff_liquido(1.0, 2.0, 0.1), rel=0.01)
        # E a promessa nominal de 2.00x não se cumpre.
        assert observado < 1.6


def passeio_aleatorio(n=15000, seed=7, vol=0.0015):
    """Série sem previsibilidade alguma, por construção.

    Serve de laboratório: se o motor reproduz aqui o acerto que a teoria
    prevê, então o número que ele mostra em dados reais também é confiável.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    hi = close * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = close * (1 - np.abs(rng.normal(0, vol / 2, n)))
    op = np.concatenate([[100.0], close[:-1]])
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="15min"),
        "open": op,
        "high": np.maximum(hi, np.maximum(op, close)),
        "low": np.minimum(lo, np.minimum(op, close)),
        "close": close, "volume": 1.0,
    })


class TestReferenciaAleatoria:
    """O piso contra o qual as estratégias precisam ser comparadas.

    Sem esta linha, 33% de acerto parece defeito das estratégias. Com ela,
    vê-se que é o que as barreiras produzem sozinhas: com stop 1% e alvo
    2%, o preço toca o stop duas vezes mais que o alvo.
    """

    def test_entrada_aleatoria_e_reprodutivel(self):
        from trading_bot.backtest.spot import _EntradaAleatoria
        a = _EntradaAleatoria(0.3, seed=1)
        b = _EntradaAleatoria(0.3, seed=1)
        c = _EntradaAleatoria(0.3, seed=2)
        sa = [a.evaluate(None).is_actionable for _ in range(50)]
        sb = [b.evaluate(None).is_actionable for _ in range(50)]
        sc = [c.evaluate(None).is_actionable for _ in range(50)]
        assert sa == sb          # mesma semente, mesmo resultado
        assert sa != sc          # sementes diferentes exploram caminhos diferentes

    def test_entrada_aleatoria_nao_olha_o_preco(self):
        """Se olhasse, deixaria de ser controle do experimento."""
        from trading_bot.backtest.spot import _EntradaAleatoria
        e = _EntradaAleatoria(0.5, seed=3)
        # Passar janelas radicalmente diferentes não muda a sequência.
        seq_a = [e.evaluate(None).is_actionable for _ in range(30)]
        e2 = _EntradaAleatoria(0.5, seed=3)
        seq_b = [e2.evaluate("qualquer coisa") .is_actionable for _ in range(30)]
        assert seq_a == seq_b

    @pytest.mark.parametrize("stop,alvo,esperado", [
        (1.0, 1.0, 50.0),
        (1.0, 2.0, 33.3),
        (1.0, 3.0, 25.0),
    ])
    def test_acerto_do_sorteio_segue_stop_sobre_stop_mais_alvo(
        self, stop, alvo, esperado
    ):
        """Num passeio aleatório o acerto é stop/(stop+alvo), e nada mais.

        É o resultado que explica por que todas as estratégias do relatório
        aterrissaram em ~33% com barreiras 2:1: não é coincidência entre
        elas, é a mecânica.
        """
        from trading_bot.backtest.spot import _EntradaAleatoria
        df = passeio_aleatorio()
        bt = SpotBacktester(
            StrategyConfig(name="rsi_reversal"), None,
            stop_loss_pct=stop, take_profit_pct=alvo,
            fee_pct=0.0, initial_balance=1000.0,
        )
        total = vitorias = 0
        for seed in range(3):
            r = bt.run(df, "aleatório", strategy=_EntradaAleatoria(0.03, seed))
            total += r.stats.total_trades
            vitorias += sum(1 for t in r.trades if t.net > 0)
        assert total > 250, "amostra do próprio teste insuficiente"
        obtido = 100 * vitorias / total
        # Fica um pouco abaixo da teoria: quando stop e alvo caem no mesmo
        # candle o motor assume stop, de propósito.
        assert esperado - 4.5 <= obtido <= esperado + 2.0

    def test_referencia_devolve_faixa_de_ruido(self):
        df = passeio_aleatorio(n=8000)
        bt = SpotBacktester(
            StrategyConfig(name="rsi_reversal"), None,
            stop_loss_pct=1.0, take_profit_pct=2.0, fee_pct=0.1,
        )
        base = bt.referencia_aleatoria(df, n_trades_alvo=120, seeds=5)
        assert base["sementes"] == 5
        assert base["win_rate_min"] <= base["win_rate"] <= base["win_rate_max"]
        assert base["win_rate_max"] > base["win_rate_min"], "faixa não pode ser um ponto"
        assert 20 <= base["win_rate"] <= 45
        assert "aleatório" in base["strategy"]

    def test_referencia_respeita_a_quantidade_pedida(self):
        df = passeio_aleatorio(n=8000)
        bt = SpotBacktester(
            StrategyConfig(name="rsi_reversal"), None,
            stop_loss_pct=1.0, take_profit_pct=2.0,
        )
        poucos = bt.referencia_aleatoria(df, n_trades_alvo=40, seeds=3)
        muitos = bt.referencia_aleatoria(df, n_trades_alvo=200, seeds=3)
        assert poucos["total_trades"] < muitos["total_trades"]

    def test_referencia_nao_quebra_com_dados_curtos(self):
        assert SpotBacktester(StrategyConfig(name="rsi_reversal")).referencia_aleatoria(
            passeio_aleatorio(n=30), 50
        ) == {}

    def test_referencia_ignora_pedido_vazio(self):
        bt = SpotBacktester(StrategyConfig(name="rsi_reversal"))
        assert bt.referencia_aleatoria(passeio_aleatorio(n=2000), 0) == {}

    def test_run_aceita_estrategia_injetada_sem_registro(self):
        """'aleatório' não existe no registro — e não deve existir."""
        from trading_bot.core.strategies import get_strategy
        with pytest.raises(KeyError):
            get_strategy("aleatório", StrategyConfig(name="rsi_reversal"))


class TestSinaisPreparados:
    """Reuso de sinais entre combinações de barreiras.

    Os sinais dependem do preço, não do stop nem do alvo. Calculá-los uma
    vez e reaproveitá-los é o que torna a varredura viável — mas só vale se
    o resultado for exatamente o mesmo do caminho direto.
    """

    @pytest.mark.parametrize("nome", [
        "rsi_reversal", "macd_momentum", "bollinger_reversion",
        "trend_pullback", "confluence",
    ])
    def test_caminho_rapido_da_resultado_identico(self, nome):
        df = passeio_aleatorio(n=4000, seed=11)
        bt = SpotBacktester(StrategyConfig(name=nome), None,
                            stop_loss_pct=1.0, take_profit_pct=2.0, fee_pct=0.1)
        direto = bt.run(df, nome)
        rapido = bt.run(df, nome, preparado=bt.preparar(df, nome))

        assert direto.stats.total_trades == rapido.stats.total_trades
        assert direto.stats.wins == rapido.stats.wins
        assert direto.stats.net_profit == pytest.approx(rapido.stats.net_profit, abs=1e-9)
        # Não basta o agregado bater: as operações têm de ser as mesmas.
        assert ([t.entry_time for t in direto.trades]
                == [t.entry_time for t in rapido.trades])
        assert ([t.exit_price for t in direto.trades]
                == [t.exit_price for t in rapido.trades])

    def test_mesmos_sinais_servem_a_barreiras_diferentes(self):
        """O preparo não pode carregar nada específico de stop/alvo."""
        df = passeio_aleatorio(n=4000, seed=12)
        bt = SpotBacktester(StrategyConfig(name="trend_pullback"), None,
                            stop_loss_pct=1.0, take_profit_pct=2.0)
        prep = bt.preparar(df, "trend_pullback")
        a = bt.run(df, "trend_pullback", preparado=prep)

        bt.stop_loss_pct, bt.take_profit_pct = 0.5, 1.5
        b = bt.run(df, "trend_pullback", preparado=prep)

        # Barreiras mais apertadas fecham antes: as operações mudam.
        assert a.stats.total_trades != b.stats.total_trades or \
            a.stats.net_profit != b.stats.net_profit
        # Mas a primeira entrada é a mesma: o sinal não mudou.
        assert a.trades[0].entry_time == b.trades[0].entry_time

    def test_densidade_de_sinais_entre_zero_e_um(self):
        df = passeio_aleatorio(n=3000, seed=13)
        bt = SpotBacktester(StrategyConfig(name="confluence"), None)
        d = bt.densidade_de_sinais(bt.preparar(df, "confluence"))
        assert 0.0 <= d <= 1.0

    def test_preparo_aleatorio_respeita_a_probabilidade(self):
        df = passeio_aleatorio(n=5000, seed=14)
        bt = SpotBacktester(StrategyConfig(name="rsi_reversal"), None)
        dados = bt.preparar(df, "rsi_reversal").data
        prep = bt.preparar_aleatorio(dados, prob=0.1, seed=0)
        marcas = sum(1 for m in prep.sinais if m is not None)
        assert 0.08 < marcas / len(dados) < 0.12

    def test_preparo_aleatorio_e_reprodutivel(self):
        df = passeio_aleatorio(n=2000, seed=15)
        bt = SpotBacktester(StrategyConfig(name="rsi_reversal"), None)
        dados = bt.preparar(df, "rsi_reversal").data
        a = bt.preparar_aleatorio(dados, 0.1, seed=4).sinais
        b = bt.preparar_aleatorio(dados, 0.1, seed=4).sinais
        c = bt.preparar_aleatorio(dados, 0.1, seed=5).sinais
        assert a == b
        assert a != c

    def test_entradas_fixas_isolam_o_efeito_das_barreiras(self):
        """Na varredura, só o stop e o alvo podem variar.

        Se as entradas mudassem junto, não daria para atribuir a diferença
        de resultado às barreiras.
        """
        df = passeio_aleatorio(n=4000, seed=16)
        bt = SpotBacktester(StrategyConfig(name="rsi_reversal"), None,
                            stop_loss_pct=1.0, take_profit_pct=2.0)
        dados = bt.preparar(df, "rsi_reversal").data
        prep = bt.preparar_aleatorio(dados, 0.02, seed=1)

        primeira_a = bt.run(df, "aleatório", preparado=prep).trades[0].entry_time
        bt.stop_loss_pct, bt.take_profit_pct = 2.0, 6.0
        primeira_b = bt.run(df, "aleatório", preparado=prep).trades[0].entry_time
        assert primeira_a == primeira_b
