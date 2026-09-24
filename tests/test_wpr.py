"""Williams %R: indicador, níveis configuráveis, entrada e saída própria."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.core.config import StrategyConfig
from trading_bot.core.indicators import enrich, williams_r
from trading_bot.core.models import Direction
from trading_bot.core.strategies import get_strategy
from trading_bot.backtest.spot import SpotBacktester


def serie(valores):
    return pd.Series([float(v) for v in valores])


def candles(fechamentos, folga=0.0):
    """OHLC em que a máxima/mínima do candle é o próprio fechamento.

    Com folga=0 o WPR depende só dos fechamentos, o que torna o valor
    esperado calculável à mão.
    """
    n = len(fechamentos)
    c = np.array([float(x) for x in fechamentos])
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"),
        "open": c, "high": c + folga, "low": c - folga, "close": c,
        "volume": np.ones(n),
    })


class TestIndicador:
    def test_fechou_na_minima_da_janela(self):
        w = williams_r(serie([5, 4, 3, 2, 1]), serie([5, 4, 3, 2, 1]),
                       serie([5, 4, 3, 2, 1]), 5)
        assert w.iloc[-1] == pytest.approx(-100.0)

    def test_fechou_na_maxima_da_janela(self):
        w = williams_r(serie([1, 2, 3, 4, 5]), serie([1, 2, 3, 4, 5]),
                       serie([1, 2, 3, 4, 5]), 5)
        assert w.iloc[-1] == pytest.approx(0.0)

    def test_meio_da_faixa(self):
        h, l, c = serie([10] * 5), serie([0] * 5), serie([0, 0, 0, 0, 5])
        assert williams_r(h, l, c, 5).iloc[-1] == pytest.approx(-50.0)

    def test_quarto_superior(self):
        h, l, c = serie([100] * 4), serie([0] * 4), serie([0, 0, 0, 75])
        assert williams_r(h, l, c, 4).iloc[-1] == pytest.approx(-25.0)

    def test_nunca_sai_da_faixa_de_menos_cem_a_zero(self):
        rng = np.random.default_rng(7)
        c = pd.Series(100 + rng.normal(0, 2, 400).cumsum())
        w = williams_r(c + 1, c - 1, c, 20).dropna()
        assert w.min() >= -100.0 and w.max() <= 0.0

    def test_mercado_parado_vira_meio_da_faixa_e_nao_nan(self):
        # Divisão 0/0. Propagar NaN faria a estratégia cegar por 20 candles
        # depois que o mercado voltasse a andar.
        flat = serie([50] * 10)
        w = williams_r(flat, flat, flat, 5)
        assert w.iloc[-1] == pytest.approx(-50.0)
        assert not w.iloc[4:].isna().any()

    def test_periodo_incompleto_fica_nan(self):
        w = williams_r(serie([1, 2, 3]), serie([1, 2, 3]), serie([1, 2, 3]), 5)
        assert w.isna().all()

    def test_janela_desliza_e_esquece_o_passado(self):
        # A máxima 200 sai da janela de 3 e o WPR deve subir de volta.
        h = serie([100, 200, 100, 100, 100])
        w = williams_r(h, h, h, 3)
        assert w.iloc[2] == pytest.approx(-100.0)  # 200 ainda pesa
        assert w.iloc[4] == pytest.approx(-50.0)   # já esqueceu


class TestConfiguracao:
    def test_valores_padrao_sao_os_pedidos(self):
        c = StrategyConfig()
        assert c.wpr_period == 20
        assert c.wpr_buy == -95.0
        assert c.wpr_sell == -5.0
        assert c.wpr_exit_buy == -20.0
        assert c.wpr_exit_sell == -80.0

    def test_niveis_vem_do_ambiente(self, monkeypatch):
        monkeypatch.setenv("STRAT_WPR_PERIOD", "34")
        monkeypatch.setenv("STRAT_WPR_BUY", "-90")
        monkeypatch.setenv("STRAT_WPR_EXIT_BUY", "-30")
        c = StrategyConfig()
        assert (c.wpr_period, c.wpr_buy, c.wpr_exit_buy) == (34, -90.0, -30.0)

    @pytest.mark.parametrize("campo,valor", [
        ("wpr_buy", -101.0), ("wpr_sell", 1.0), ("wpr_period", 1),
    ])
    def test_valores_impossiveis_sao_recusados(self, campo, valor):
        with pytest.raises(Exception):
            StrategyConfig(**{campo: valor})

    def test_saida_da_compra_abaixo_da_entrada_e_recusada(self):
        with pytest.raises(Exception, match="EXIT_BUY"):
            StrategyConfig(wpr_buy=-20.0, wpr_exit_buy=-40.0)

    def test_saida_da_venda_acima_da_entrada_e_recusada(self):
        with pytest.raises(Exception, match="EXIT_SELL"):
            StrategyConfig(wpr_sell=-80.0, wpr_exit_sell=-40.0)

    def test_zonas_de_compra_e_venda_nao_podem_se_cruzar(self):
        with pytest.raises(Exception, match="WPR_BUY"):
            StrategyConfig(wpr_buy=-10.0, wpr_sell=-90.0,
                           wpr_exit_buy=-5.0, wpr_exit_sell=-95.0)

    def test_enrich_usa_o_periodo_configurado(self):
        df = candles(list(range(1, 60)))
        a = enrich(df, StrategyConfig(wpr_period=5))["wpr"]
        b = enrich(df, StrategyConfig(wpr_period=50))["wpr"]
        assert a.notna().sum() > b.notna().sum()


def preparar(fechamentos, cfg=None):
    cfg = cfg or StrategyConfig(name="wpr_extremes", min_confidence=0.0)
    return enrich(candles(fechamentos), cfg), get_strategy("wpr_extremes", cfg)


class TestEntrada:
    def test_compra_no_fundo_da_faixa(self):
        # Queda contínua: o penúltimo candle fecha na mínima → WPR = -100.
        df, st = preparar(list(range(60, 20, -1)))
        s = st.generate(df)
        assert s.direction is Direction.CALL
        assert "WPR" in s.reason

    def test_venda_no_topo_da_faixa(self):
        df, st = preparar(list(range(20, 60)))
        assert st.generate(df).direction is Direction.PUT

    def test_meio_da_faixa_nao_gera_sinal(self):
        # Penúltimo candle fecha em 100 numa janela de 90 a 110 → WPR = -50.
        df, st = preparar([100] * 25 + [110, 90, 100, 100])
        assert st.generate(df).direction is Direction.NONE

    def test_respeita_nivel_de_compra_afrouxado(self):
        # WPR ≈ -50: nada com o padrão -95, compra com o nível em -40.
        precos = [100] * 25 + [110, 90, 100, 100]
        assert preparar(precos)[1].generate(preparar(precos)[0]).direction is Direction.NONE
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                             wpr_buy=-40.0, wpr_exit_buy=-10.0)
        df, st = preparar(precos, cfg)
        assert st.generate(df).direction is Direction.CALL

    def test_confianca_cresce_com_a_profundidade(self):
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                             wpr_buy=-50.0, wpr_exit_buy=-10.0)
        # WPR = -60 (raso) contra WPR = -100 (fundo).
        raso = enrich(candles([100] * 25 + [100, 80, 92, 100]), cfg)
        fundo = enrich(candles(list(range(60, 20, -1))), cfg)
        st = get_strategy("wpr_extremes", cfg)
        assert st.generate(fundo).confidence > st.generate(raso).confidence

    def test_confianca_nunca_passa_de_um(self):
        df, st = preparar(list(range(60, 20, -1)))
        assert 0.0 <= st.generate(df).confidence <= 1.0

    def test_sem_candles_suficientes_nao_quebra(self):
        df, st = preparar([100, 101, 102])
        assert st.generate(df).direction is Direction.NONE

    def test_decide_pelo_penultimo_candle(self):
        # O último candle (em formação) não pode mudar a decisão.
        base = list(range(60, 20, -1))
        df_a, st = preparar(base)
        df_b, _ = preparar(base[:-1] + [999])
        assert st.generate(df_a).direction == st.generate(df_b).direction

    def test_precisa_de_pelo_menos_o_periodo_em_candles(self):
        cfg = StrategyConfig(name="wpr_extremes", wpr_period=40)
        assert get_strategy("wpr_extremes", cfg).required_candles() >= 42


class TestSaida:
    def test_compra_sai_quando_volta_ao_miolo(self):
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0)
        st = get_strategy("wpr_extremes", cfg)
        # Sobe até fechar no topo da janela → WPR ≈ 0 > -20.
        df = enrich(candles(list(range(20, 60))), cfg)
        assert st.should_exit(df, Direction.CALL) is True

    def test_compra_nao_sai_enquanto_o_wpr_esta_no_fundo(self):
        cfg = StrategyConfig(name="wpr_extremes")
        st = get_strategy("wpr_extremes", cfg)
        df = enrich(candles(list(range(60, 20, -1))), cfg)
        assert st.should_exit(df, Direction.CALL) is False

    def test_venda_sai_quando_o_wpr_desaba(self):
        cfg = StrategyConfig(name="wpr_extremes")
        st = get_strategy("wpr_extremes", cfg)
        df = enrich(candles(list(range(60, 20, -1))), cfg)
        assert st.should_exit(df, Direction.PUT) is True

    def test_venda_nao_sai_no_topo(self):
        cfg = StrategyConfig(name="wpr_extremes")
        st = get_strategy("wpr_extremes", cfg)
        df = enrich(candles(list(range(20, 60))), cfg)
        assert st.should_exit(df, Direction.PUT) is False

    def test_nivel_de_saida_configuravel_muda_a_decisao(self):
        # WPR ≈ -50 no penúltimo candle.
        precos = [100] * 25 + [110, 90, 100, 100]
        cedo = StrategyConfig(name="wpr_extremes", wpr_exit_buy=-70.0)
        tarde = StrategyConfig(name="wpr_extremes", wpr_exit_buy=-10.0)
        assert get_strategy("wpr_extremes", cedo).should_exit(
            enrich(candles(precos), cedo), Direction.CALL) is True
        assert get_strategy("wpr_extremes", tarde).should_exit(
            enrich(candles(precos), tarde), Direction.CALL) is False

    def test_sem_wpr_calculado_nao_sai(self):
        cfg = StrategyConfig(name="wpr_extremes")
        st = get_strategy("wpr_extremes", cfg)
        df = enrich(candles([100] * 5), cfg)   # warmup incompleto → NaN
        assert st.should_exit(df, Direction.CALL) is False

    def test_dataframe_curto_demais_nao_quebra(self):
        cfg = StrategyConfig(name="wpr_extremes")
        st = get_strategy("wpr_extremes", cfg)
        assert st.should_exit(enrich(candles([100]), cfg), Direction.CALL) is False

    def test_estrategias_antigas_nao_tem_saida_propria(self):
        # Contrato: quem não define should_exit continua saindo só por
        # stop/alvo. Se isso mudar sem querer, os resultados históricos
        # deixam de ser comparáveis.
        cfg = StrategyConfig(name="rsi_reversal")
        st = get_strategy("rsi_reversal", cfg)
        df = enrich(candles(list(range(20, 60))), cfg)
        assert st.should_exit(df, Direction.CALL) is False


# O motor precisa de aquecimento (required_candles) antes de aceitar o
# primeiro sinal, e é long-only por padrão. Então o mergulho que dispara a
# compra tem que vir DEPOIS de uma faixa lateral longa o bastante.
LATERAL = [100, 101, 99, 100.5, 99.5] * 24      # 120 candles
MERGULHO = list(np.linspace(99.5, 70, 25))      # exaustão vendedora → WPR ≈ -100
REPIQUE = list(np.linspace(70, 105, 40))        # volta ao topo → saída pelo WPR
PERCURSO = LATERAL + MERGULHO + REPIQUE


class TestSaidaNoBacktest:
    def _motor(self, cfg):
        return SpotBacktester(cfg, None, stop_loss_pct=50.0, take_profit_pct=50.0,
                              fee_pct=0.0, max_bars=500)

    def test_operacao_fecha_pelo_sinal_e_nao_pelo_stop(self):
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                             min_atr_pct=0.0, max_atr_pct=100.0)
        # Cai fundo (compra) e depois sobe forte (saída pelo WPR). Stop e
        # alvo em 50% são largos demais para disparar.
        r = self._motor(cfg).run(candles(PERCURSO, folga=0.2), "wpr_extremes")
        assert len(r.trades) > 0
        assert any(t.reason == "saída da estratégia" for t in r.trades)

    def test_saida_da_estrategia_nao_usa_preco_do_futuro(self):
        # A saída executa na ABERTURA do candio seguinte à decisão, nunca
        # no fechamento do candle que ainda estava se formando.
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                             min_atr_pct=0.0, max_atr_pct=100.0)
        df = candles(PERCURSO, folga=0.2)
        r = self._motor(cfg).run(df, "wpr_extremes")
        aberturas = df["open"].to_numpy(dtype=float)
        saidas = [t for t in r.trades if t.reason == "saída da estratégia"]
        assert saidas, "o percurso precisa produzir ao menos uma saída por sinal"
        for t in saidas:
            # O preço de saída tem que ser a abertura de ALGUM candle — se
            # fosse o fechamento do candle da decisão, seria informação que
            # ainda não existia no momento de decidir.
            assert np.isclose(aberturas, t.exit_price).any()

    def test_estrategia_sem_saida_propria_continua_igual(self):
        cfg = StrategyConfig(name="rsi_reversal", min_confidence=0.0,
                             min_atr_pct=0.0, max_atr_pct=100.0)
        rng = np.random.default_rng(3)
        precos = 100 + rng.normal(0, 1, 600).cumsum()
        r = SpotBacktester(cfg, None, stop_loss_pct=1.0, take_profit_pct=2.0,
                           fee_pct=0.0, max_bars=30).run(
                               candles(precos, folga=0.3), "rsi_reversal")
        assert all(t.reason != "saída da estratégia" for t in r.trades)

    def test_stop_tem_prioridade_sobre_a_saida_por_sinal(self):
        # Stop apertado: se o preço perfura o stop no mesmo candle em que o
        # sinal mandaria sair, o stop é que vale (premissa pessimista).
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                             min_atr_pct=0.0, max_atr_pct=100.0)
        r = SpotBacktester(cfg, None, stop_loss_pct=0.1, take_profit_pct=50.0,
                           fee_pct=0.0, max_bars=500).run(
                               candles(PERCURSO, folga=0.5), "wpr_extremes")
        assert any(t.reason == "stop" for t in r.trades)


class TestPernaVendida:
    """A especificação tem duas pernas; o spot é long-only por padrão."""

    def _cfg(self):
        return StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                              min_atr_pct=0.0, max_atr_pct=100.0)

    def _percurso_invertido(self):
        # Espelho do PERCURSO: sobe ao topo (venda) e depois desaba (saída).
        return (LATERAL + list(np.linspace(100.5, 130, 25))
                + list(np.linspace(130, 95, 40)))

    def test_sem_allow_short_a_venda_e_ignorada(self):
        r = SpotBacktester(self._cfg(), None, stop_loss_pct=50.0,
                           take_profit_pct=50.0, fee_pct=0.0, max_bars=500).run(
                               candles(self._percurso_invertido(), folga=0.2),
                               "wpr_extremes")
        assert all(t.direction != "SHORT" for t in r.trades)

    def test_com_allow_short_a_venda_opera(self):
        r = SpotBacktester(self._cfg(), None, stop_loss_pct=50.0,
                           take_profit_pct=50.0, fee_pct=0.0, max_bars=500,
                           allow_short=True).run(
                               candles(self._percurso_invertido(), folga=0.2),
                               "wpr_extremes")
        vendas = [t for t in r.trades if t.direction == "SHORT"]
        assert vendas, "a perna vendida precisa produzir operações"

    def test_venda_tambem_fecha_pela_regra_da_estrategia(self):
        r = SpotBacktester(self._cfg(), None, stop_loss_pct=50.0,
                           take_profit_pct=50.0, fee_pct=0.0, max_bars=500,
                           allow_short=True).run(
                               candles(self._percurso_invertido(), folga=0.2),
                               "wpr_extremes")
        assert any(t.direction == "SHORT" and t.reason == "saída da estratégia"
                   for t in r.trades)


class TestAvisoDeSaidaAoVivo:
    """O motor ao vivo não executa should_exit — isso não pode ficar mudo."""

    def _engine(self, nome):
        from unittest.mock import MagicMock
        from trading_bot.core.engine import TradingEngine
        from trading_bot.core.config import Settings

        st = Settings(strategy=StrategyConfig(name=nome))
        broker, storage = MagicMock(), MagicMock()
        eng = TradingEngine.__new__(TradingEngine)
        eng.settings, eng.broker, eng.storage = st, broker, storage
        eng.strategy = get_strategy(nome, st.strategy)
        return eng, storage

    def test_estrategia_com_saida_propria_gera_aviso(self):
        eng, storage = self._engine("wpr_extremes")
        assert eng._avisar_sobre_saida_da_estrategia() is True
        assert storage.log_event.called
        nivel, origem = storage.log_event.call_args[0][0], storage.log_event.call_args[0][1]
        assert nivel == "WARNING" and origem == "engine"

    def test_estrategia_sem_saida_propria_nao_avisa(self):
        eng, storage = self._engine("rsi_reversal")
        assert eng._avisar_sobre_saida_da_estrategia() is False
        assert not storage.log_event.called

    def test_o_aviso_diz_o_que_diverge(self):
        eng, storage = self._engine("wpr_extremes")
        eng._avisar_sobre_saida_da_estrategia()
        texto = storage.log_event.call_args[0][2]
        assert "saída" in texto.lower()


class TestEquilibrioComSaidaPropria:
    """O equilíbrio nominal (stop/alvo) não vale para quem sai pelo sinal.

    Esta classe existe por um erro real: o relatório anunciou "+16,6pp acima
    do equilíbrio de 30,0%" para uma estratégia que PERDEU dinheiro, porque
    comparava o acerto com o equilíbrio deduzido de stop e alvo enquanto as
    saídas aconteciam noutro lugar.
    """

    def _resultado(self):
        cfg = StrategyConfig(name="wpr_extremes", min_confidence=0.0,
                             min_atr_pct=0.0, max_atr_pct=100.0)
        # Barreiras largas de propósito: o objetivo é que a SAÍDA PELO
        # SINAL aconteça. Com stop apertado ele dispara antes e o cenário
        # que queremos medir não chega a existir.
        bt = SpotBacktester(cfg, None, stop_loss_pct=20.0, take_profit_pct=60.0,
                            fee_pct=0.1, max_bars=500)
        return bt.run(candles(PERCURSO, folga=0.3), "wpr_extremes")

    def test_conta_as_saidas_pela_regra_da_estrategia(self):
        r = self._resultado()
        esperado = sum(1 for t in r.trades if t.reason == "saída da estratégia")
        assert r.saidas_por_sinal == esperado
        assert r.saidas_por_sinal > 0

    def test_estrategia_sem_saida_propria_conta_zero(self):
        cfg = StrategyConfig(name="rsi_reversal", min_confidence=0.0,
                             min_atr_pct=0.0, max_atr_pct=100.0)
        rng = np.random.default_rng(3)
        precos = 100 + rng.normal(0, 1, 600).cumsum()
        r = SpotBacktester(cfg, None, stop_loss_pct=1.0, take_profit_pct=2.0,
                           fee_pct=0.0, max_bars=30).run(
                               candles(precos, folga=0.3), "rsi_reversal")
        assert r.saidas_por_sinal == 0

    def test_o_resumo_expoe_o_contador(self):
        assert "saidas_por_sinal" in self._resultado().to_dict()["summary"]

    def test_equilibrio_vem_do_payoff_observado_nao_do_alvo(self):
        # Com alvo 3x o stop, o equilíbrio nominal é ~30%. Saindo cedo o
        # payoff despenca e o equilíbrio real sobe muito acima disso.
        r = self._resultado()
        if r.payoff_ratio and r.payoff_ratio < 1.0:
            assert r.breakeven_win_rate > 50.0

    def test_acerto_alto_com_payoff_baixo_ainda_reprova(self):
        # O caso que enganou: 46,6% de acerto e prejuízo. O veredito tem de
        # olhar o dinheiro, não o acerto.
        r = self._resultado()
        if r.stats.net_profit <= 0:
            # Pode sair "amostra insuficiente" quando há poucas operações;
            # o que NUNCA pode sair é aprovação para quem perdeu dinheiro.
            assert "APROVADA" not in r._verdict()


class TestRelatorioNaoUsaEquilibrioNominal:
    """Trava de código: o texto de leitura não pode voltar a usar be_liq."""

    def _bloco(self):
        from pathlib import Path
        from trading_bot import cli
        # Pelo módulo, não por caminho relativo: o pytest pode rodar de
        # qualquer diretório.
        s = Path(cli.__file__).read_text(encoding="utf-8")
        i = s.index("def cmd_backtest_spot")
        return s[i:s.index("\ndef ", i + 10)]

    def test_a_tabela_mostra_o_equilibrio_por_linha(self):
        b = self._bloco()
        assert "equilíb." in b
        assert 'r.get("breakeven_win_rate"' in b

    def test_a_leitura_usa_o_equilibrio_da_estrategia(self):
        b = self._bloco()
        assert 'be_real = melhor.get("breakeven_win_rate"' in b
        # o erro original: comparar o acerto com o equilíbrio nominal
        assert 'falta_be = melhor["win_rate"] - be_liq' not in b

    def test_avisa_quando_os_acertos_nao_sao_comparaveis(self):
        assert 'melhor.get("saidas_por_sinal")' in self._bloco()
