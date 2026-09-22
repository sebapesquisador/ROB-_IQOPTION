"""
Validação fora da amostra.

Comparar N estratégias e ficar com a melhor infla o resultado mesmo quando
nenhuma tem vantagem. Simulação com 5 estratégias de acerto idêntico ao
ponto de equilíbrio: a "campeã" aparenta ~+9pp só por ruído. A separação
temporal (escolher no passado, julgar no futuro) é o que distingue vantagem
real de sorte do período.
"""
import numpy as np
import pandas as pd
import pytest

from trading_bot.cli import _run_holdout


class FakeBacktester:
    """Devolve resultados fixos por fatia, sem depender de dados de mercado."""

    def __init__(self, por_fatia):
        self.por_fatia = por_fatia
        self.chamadas = []

    def compare(self, df, names, symbol):
        fatia = "treino" if len(df) == self.por_fatia["n_treino"] else "teste"
        self.chamadas.append((fatia, tuple(names), len(df)))
        return [r for r in self.por_fatia[fatia] if r["strategy"] in names]


def make_res(nome, trades, win_rate, edge, lucro, p=0.5):
    return {"strategy": nome, "total_trades": trades, "win_rate": win_rate,
            "edge_pp": edge, "net_profit": lucro, "p_value": p}


class Args:
    holdout = True
    holdout_split = 0.7


def make_df(n):
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"),
        "close": np.linspace(1.1, 1.2, n),
    })


def run(capsys, treino, teste, n=1000):
    df = make_df(n)
    split = int(n * 0.7)
    bt = FakeBacktester({"n_treino": split, "treino": treino, "teste": teste})
    code = _run_holdout(bt, df, [r["strategy"] for r in treino], "EURUSD", Args())
    return code, capsys.readouterr().out, bt


class TestSelecao:
    def test_escolhe_a_de_maior_lucro(self, capsys):
        treino = [make_res("perdedora", 100, 45.0, -9.0, -200.0),
                  make_res("campea", 100, 60.0, +6.0, +150.0),
                  make_res("media", 100, 52.0, -2.0, -30.0)]
        teste = [make_res("campea", 50, 58.0, +4.0, +60.0, p=0.04)]
        _, out, bt = run(capsys, treino, teste)
        assert "campeã na seleção: campea" in out
        # a fatia de teste roda apenas a campeã, não as 3
        assert bt.chamadas[1][1] == ("campea",)

    def test_nao_vaza_dados_entre_fatias(self, capsys):
        """Seleção e teste usam candles disjuntos."""
        treino = [make_res("a", 100, 60.0, +6.0, +100.0)]
        teste = [make_res("a", 40, 55.0, +1.0, +10.0)]
        _, _, bt = run(capsys, treino, teste, n=1000)
        n_treino, n_teste = bt.chamadas[0][2], bt.chamadas[1][2]
        assert n_treino == 700 and n_teste == 300
        assert n_treino + n_teste == 1000

    def test_respeita_split_customizado(self, capsys):
        class A(Args):
            holdout_split = 0.5
        df = make_df(1000)
        bt = FakeBacktester({"n_treino": 500,
                             "treino": [make_res("a", 100, 60.0, 6.0, 100.0)],
                             "teste": [make_res("a", 50, 55.0, 1.0, 10.0)]})
        _run_holdout(bt, df, ["a"], "EURUSD", A())
        assert bt.chamadas[0][2] == 500


class TestVeredito:
    def test_vantagem_some_e_reprovada(self, capsys):
        """O caso que mais importa: bonito na seleção, ruim no teste."""
        treino = [make_res("a", 200, 60.0, +6.0, +300.0)]
        teste = [make_res("a", 80, 50.0, -4.0, -62.96)]
        _, out, _ = run(capsys, treino, teste)
        assert "REPROVADA FORA DA AMOSTRA" in out

    def test_sobrevive_com_significancia(self, capsys):
        treino = [make_res("a", 500, 60.0, +6.0, +400.0)]
        teste = [make_res("a", 300, 59.0, +5.0, +200.0, p=0.001)]
        _, out, _ = run(capsys, treino, teste)
        assert "SOBREVIVEU" in out

    def test_mantem_vantagem_sem_significancia(self, capsys):
        treino = [make_res("a", 200, 60.0, +6.0, +300.0)]
        teste = [make_res("a", 40, 57.0, +3.0, +20.0, p=0.30)]
        _, out, _ = run(capsys, treino, teste)
        assert "NÃO COMPROVADA" in out

    def test_poucos_trades_e_inconclusivo(self, capsys):
        treino = [make_res("a", 200, 60.0, +6.0, +300.0)]
        teste = [make_res("a", 12, 66.0, +12.0, +40.0, p=0.02)]
        _, out, _ = run(capsys, treino, teste)
        assert "INCONCLUSIVO" in out

    def test_inconclusivo_tem_prioridade_sobre_sobreviveu(self, capsys):
        """Amostra minúscula não vira aprovação, mesmo com p baixo."""
        treino = [make_res("a", 200, 60.0, +6.0, +300.0)]
        teste = [make_res("a", 5, 80.0, +26.0, +30.0, p=0.001)]
        _, out, _ = run(capsys, treino, teste)
        assert "SOBREVIVEU" not in out


class TestRelatorio:
    def test_queda_tem_sinal_negativo(self, capsys):
        """Regressão: 54,1% → 50,0% era exibido como +4.1pp."""
        treino = [make_res("a", 200, 54.1, +0.05, -8.34)]
        teste = [make_res("a", 82, 50.0, -4.0, -62.96)]
        _, out, _ = run(capsys, treino, teste)
        assert "-4.1pp" in out
        assert "+4.1pp" not in out

    def test_melhora_tem_sinal_positivo(self, capsys):
        treino = [make_res("a", 200, 50.0, -4.0, -50.0)]
        teste = [make_res("a", 82, 54.1, +0.05, +5.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "+4.1pp" in out


class TestCasosLimite:
    def test_sem_resultado_na_selecao(self, capsys):
        code, out, _ = run(capsys, [], [])
        assert code == 1
        assert "Nenhuma estratégia" in out

    def test_campea_sem_trades_no_teste(self, capsys):
        treino = [make_res("a", 200, 60.0, +6.0, +300.0)]
        code, out, _ = run(capsys, treino, [])
        assert code == 1
        assert "não gerou operações" in out
