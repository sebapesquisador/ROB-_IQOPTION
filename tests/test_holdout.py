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


def make_res(nome, trades, win_rate, edge, lucro, p=0.5, stake=10.0):
    """Espelha as chaves reais de BacktestResult.to_dict()["summary"]."""
    wins = round(trades * win_rate / 100)
    losses = trades - wins
    return {"strategy": nome, "total_trades": trades, "win_rate": win_rate,
            "edge_pp": edge, "net_profit": lucro, "p_value": p,
            "wins": wins, "losses": losses,
            "gross_loss": -losses * stake}


class Args:
    holdout = True
    holdout_split = 0.7
    payout = 0.85
    balance = 1000.0


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
        # o veredito acompanha a campeã da seleção, mesmo com todas avaliadas
        assert "← campeã da seleção" in out

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


class TestTodasNoTeste:
    """
    O holdout avalia todas as estratégias fora da amostra, não só a campeã.

    Ver as demais revela quando a liderança apenas troca de nome entre
    períodos — sintoma clássico de ranking movido a ruído. Num teste real,
    bollinger_reversion liderou a seleção e rsi_reversal (a PIOR, -19,8pp)
    liderou o holdout.
    """

    def test_avalia_todas_fora_da_amostra(self, capsys):
        treino = [make_res("campea", 200, 60.0, +6.0, +300.0),
                  make_res("outra", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("campea", 80, 52.0, -2.0, -30.0),
                 make_res("outra", 80, 56.0, +2.0, +40.0)]
        _, out, bt = run(capsys, treino, teste)
        # a segunda chamada pede as duas, não apenas a campeã
        assert set(bt.chamadas[1][1]) == {"campea", "outra"}
        assert "outra" in out.split("2) TESTE")[1]

    def test_avisa_quando_lideranca_troca(self, capsys):
        treino = [make_res("campea", 200, 60.0, +6.0, +300.0),
                  make_res("outra", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("campea", 80, 52.0, -2.0, -30.0),
                 make_res("outra", 80, 56.0, +2.0, +40.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "A melhor no teste foi outra" in out
        assert "sinal de ruído" in out

    def test_nao_avisa_quando_lideranca_se_mantem(self, capsys):
        treino = [make_res("campea", 200, 60.0, +6.0, +300.0),
                  make_res("outra", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("campea", 80, 58.0, +4.0, +90.0, p=0.02),
                 make_res("outra", 80, 49.0, -5.0, -40.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "A melhor no teste foi" not in out

    def test_veredito_segue_a_campea_nao_a_nova_lider(self, capsys):
        """A nova líder não é promovida: seria escolher olhando o resultado."""
        treino = [make_res("campea", 200, 60.0, +6.0, +300.0),
                  make_res("outra", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("campea", 80, 50.0, -4.0, -62.0),
                 make_res("outra", 80, 57.0, +3.0, +50.0, p=0.01)]
        _, out, _ = run(capsys, treino, teste)
        assert "REPROVADA FORA DA AMOSTRA" in out
        assert "SOBREVIVEU" not in out


class TestCampeaSemSignificancia:
    """
    Campeã sem significância estatística tende a ser a mais sortuda.

    Caso real: rsi_reversal liderou a seleção com 31 operações, p=0,162 e
    64,5% de acerto, e caiu para 53,9% em 13 operações no holdout — em cima
    do ponto de equilíbrio. Um limiar fixo de "30 trades" a deixava passar
    raspando; o p-valor não deixa.
    """

    CASO_REAL = [
        ("rsi_reversal", 31, 64.5, +10.5, +60.48, 0.162),
        ("macd_momentum", 109, 52.8, -1.3, -29.67, 0.680),
        ("bollinger_reversion", 117, 49.1, -4.9, -104.66, 0.894),
        ("trend_pullback", 227, 49.3, -4.7, -186.34, 0.948),
        ("confluence", 815, 49.4, -4.7, -516.73, 0.999),
    ]

    def test_caso_real_dispara_o_aviso(self, capsys):
        """31 operações passavam pelo limiar de 30; p=0,162 não passa."""
        treino = [make_res(*c) for c in self.CASO_REAL]
        teste = [make_res(n, 40, 50.0, -4.0, -20.0) for n, *_ in self.CASO_REAL]
        _, out, _ = run(capsys, treino, teste)
        assert "não tem significância estatística" in out
        assert "p=0.162" in out

    def test_aponta_desproporcao_de_amostra(self, capsys):
        """A campeã opera 3,8x menos que a mediana do grupo (31 vs 117)."""
        treino = [make_res(*c) for c in self.CASO_REAL]
        teste = [make_res(n, 40, 50.0, -4.0, -20.0) for n, *_ in self.CASO_REAL]
        _, out, _ = run(capsys, treino, teste)
        assert "3.8x menos que a mediana" in out
        assert "31 vs 117" in out

    def test_amostra_grande_sem_significancia_nao_culpa_o_tamanho(self, capsys):
        """209 operações não é 'amostra pequena' — a mensagem deve mudar."""
        treino = [make_res("a", 209, 54.1, +0.05, -8.34, 0.527),
                  make_res("b", 112, 50.9, -3.2, -67.89, 0.778)]
        teste = [make_res("a", 82, 50.0, -4.0, -62.96),
                 make_res("b", 59, 47.5, -6.6, -71.87)]
        _, out, _ = run(capsys, treino, teste)
        assert "dentro do que o acaso produz" in out
        assert "amostras pequenas" not in out

    def test_sugere_alternativa_com_significancia(self, capsys):
        # a sortuda lucra mais (vira campeã) mas sem significância;
        # a solida lucra menos e tem p baixo -> deve ser a sugerida
        treino = [make_res("sortuda", 20, 70.0, +16.0, +190.0, 0.30),
                  make_res("solida", 400, 58.0, +4.0, +150.0, 0.004)]
        teste = [make_res("sortuda", 40, 52.0, -2.0, -10.0),
                 make_res("solida", 200, 57.0, +3.0, +60.0, 0.008)]
        _, out, _ = run(capsys, treino, teste)
        assert "a melhor seria solida" in out

    def test_avisa_quando_nenhuma_tem_significancia(self, capsys):
        treino = [make_res(*c) for c in self.CASO_REAL]
        teste = [make_res(n, 40, 50.0, -4.0, -20.0) for n, *_ in self.CASO_REAL]
        _, out, _ = run(capsys, treino, teste)
        assert "Nenhuma das estratégias atingiu significância" in out
        assert "não uma aposta validada" in out

    def test_campea_significativa_nao_dispara_aviso(self, capsys):
        treino = [make_res("boa", 500, 60.0, +6.0, +400.0, 0.001),
                  make_res("outra", 300, 50.0, -4.0, -100.0, 0.900)]
        teste = [make_res("boa", 200, 59.0, +5.0, +180.0, 0.002),
                 make_res("outra", 150, 49.0, -5.0, -60.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "não tem significância" not in out


class TestAgregado:
    """
    A soma das estratégias fora da amostra revela se o conjunto está apenas
    pagando a vantagem da casa. No teste real do usuário, as 5 estratégias
    somaram -7,52% por operação contra os -7,50% teóricos do payout 85%.
    """

    def test_mostra_quantas_ficaram_positivas(self, capsys):
        treino = [make_res("a", 200, 60.0, +6.0, +300.0),
                  make_res("b", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("a", 100, 52.0, -2.0, -30.0),
                 make_res("b", 100, 51.0, -3.0, -40.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "0 de 2 positivas" in out

    def test_soma_operacoes_e_lucro(self, capsys):
        treino = [make_res("a", 200, 60.0, +6.0, +300.0),
                  make_res("b", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("a", 100, 52.0, -2.0, -30.0),
                 make_res("b", 150, 51.0, -3.0, -40.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "250 operações" in out
        assert "-70.00" in out

    def test_conta_positivas_corretamente(self, capsys):
        treino = [make_res("a", 200, 60.0, +6.0, +300.0),
                  make_res("b", 200, 50.0, -4.0, -100.0)]
        teste = [make_res("a", 100, 56.0, +2.0, +50.0, p=0.04),
                 make_res("b", 100, 51.0, -3.0, -40.0)]
        _, out, _ = run(capsys, treino, teste)
        assert "1 de 2 positivas" in out
