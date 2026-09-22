"""
Regressão: o veredito aprovava vantagem que era apenas sorte.

Caso real que motivou estes testes — backtest de 43 dias do EURUSD:
rsi_reversal fechou 30 vitórias em 45 trades (66,7%, +12,6pp sobre o
equilíbrio) e recebeu "APROVADA". O teste binomial devolve p=0,0595:
o acaso produz esse resultado em ~1 de cada 17 amostras. Somando que
5 estratégias foram comparadas e ficamos com a melhor, a chance de ao
menos uma parecer boa sem ter vantagem alguma era de ~26%.
"""
import math

import pytest

from trading_bot.backtest.engine import BacktestResult


def make_result(trades: int, wins: int, payout: float = 0.85,
                drawdown: float = 5.0) -> BacktestResult:
    r = BacktestResult(
        strategy="teste", symbol="EURUSD", payout=payout,
        initial_balance=1000.0, final_balance=1000.0,
        breakeven_win_rate=100.0 / (1.0 + payout),
    )
    r.stats.total_trades = trades
    r.stats.wins = wins
    r.stats.losses = trades - wins
    r.stats.max_drawdown_pct = drawdown
    return r


class TestPValor:
    def test_bate_com_binomial_exato(self):
        """Confere contra o valor fechado da distribuição binomial."""
        r = make_result(45, 30)
        p = 100.0 / 1.85 / 100.0
        esperado = sum(math.comb(45, i) * p**i * (1 - p)**(45 - i)
                       for i in range(30, 46))
        assert r.p_value == pytest.approx(esperado, abs=1e-12)

    def test_caso_real_rsi_reversal(self):
        """30/45 = 66,7% de acerto não é estatisticamente significativo."""
        p = make_result(45, 30).p_value
        assert p == pytest.approx(0.0595995, abs=1e-6)
        assert p > 0.01   # acima do limiar corrigido: não comprova vantagem

    def test_amostra_grande_nao_estoura(self):
        """math.comb(1193, 594) estoura o float; o cálculo é em log."""
        r = make_result(1193, 594)
        assert 0.0 <= r.p_value <= 1.0
        assert r.p_value == pytest.approx(0.9985565, abs=1e-6)

    def test_sem_trades(self):
        assert make_result(0, 0).p_value == 1.0

    def test_zero_vitorias(self):
        assert make_result(50, 0).p_value == 1.0

    def test_todas_vitorias_e_significativo(self):
        assert make_result(30, 30).p_value < 1e-6

    def test_monotonico_em_vitorias(self):
        """Mais vitórias com o mesmo n => p-valor menor."""
        ps = [make_result(100, k).p_value for k in (50, 60, 70, 80)]
        assert ps == sorted(ps, reverse=True)


class TestVeredito:
    def test_sorte_nao_e_aprovada(self):
        """O caso que passou indevidamente antes da correção."""
        v = make_result(45, 30)._verdict()
        assert "NÃO COMPROVADA" in v
        assert "APROVADA:" not in v

    def test_vantagem_real_e_aprovada(self):
        """Amostra grande com vantagem consistente deve passar."""
        v = make_result(2000, 1200, drawdown=10.0)._verdict()
        assert v.startswith("APROVADA")

    def test_amostra_pequena_barrada_antes(self):
        assert "insuficiente" in make_result(20, 15)._verdict()

    def test_abaixo_do_equilibrio_reprovada(self):
        assert "REPROVADA" in make_result(500, 240)._verdict()

    def test_drawdown_alto_marca_arriscada(self):
        v = make_result(2000, 1200, drawdown=45.0)._verdict()
        assert "ARRISCADA" in v

    def test_correcao_por_comparacoes_multiplas(self):
        """O limiar exigido é 0.05/5, não 0.05."""
        assert BacktestResult.ALPHA / BacktestResult.N_COMPARISONS == pytest.approx(0.01)

    def test_p_valor_exposto_no_dict(self):
        assert "p_value" in make_result(45, 30).to_dict()["summary"]
