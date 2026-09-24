"""Funding rate: o primeiro dado do projeto que não é o preço.

As cinco estratégias anteriores liam só a cotação e todas empataram com
entradas sorteadas. O funding é um pagamento real entre participantes, não
uma função do histórico — pode não prever nada, mas a hipótese ao menos não
é circular.

Estes testes cobrem três riscos distintos:
  * a coleta (paginação, símbolo inválido, ordem, duplicatas)
  * o alinhamento (look-ahead: o erro mais caro do código antigo)
  * a estatística (detecta o que existe, não inventa o que não existe)
"""
from __future__ import annotations

import json
import io
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Importado como módulo de propósito: `teste_permutacao` começa com "test" e
# o pytest tentaria coletá-lo como caso de teste se viesse para este namespace.
from trading_bot.backtest import funding_signal as fs
from trading_bot.backtest.funding_signal import alinhar, dividir, por_quantil
from trading_bot.data.funding import (FundingError, baixar_funding,
                                      rendimento_carry)

T0 = pd.Timestamp("2026-01-01", tz="UTC")
OITO_H = 8 * 3600 * 1000


def resposta(itens):
    """Imita o corpo JSON que a API devolve."""
    return io.BytesIO(json.dumps(itens).encode())


class Conexao:
    """urlopen devolve um context manager; o fake precisa ser um também."""

    def __init__(self, itens):
        self._corpo = resposta(itens)

    def __enter__(self):
        return self._corpo

    def __exit__(self, *exc):
        return False


def eventos(n, inicio_ms=None, taxa=0.0001):
    base = inicio_ms if inicio_ms is not None else int(T0.timestamp() * 1000)
    return [{"symbol": "BTCUSDT", "fundingTime": base + i * OITO_H,
             "fundingRate": f"{taxa:.8f}"} for i in range(n)]


class TestColeta:
    def test_converte_tipos_e_ordena(self):
        with patch("urllib.request.urlopen") as mock:
            mock.return_value.__enter__.return_value = resposta(eventos(5))
            df = baixar_funding("BTCUSDT", 5)
        assert list(df.columns) == ["timestamp", "rate"]
        assert df["rate"].dtype == float
        assert df["timestamp"].is_monotonic_increasing

    def test_pagina_quando_pedem_mais_que_o_teto(self):
        """1000 é o limite da API. Truncar em silêncio já custou caro aqui."""
        chamadas = []

        def fake(url, timeout=None):
            chamadas.append(url)
            base = int(T0.timestamp() * 1000) - len(chamadas) * 1000 * OITO_H
            n = 1000 if len(chamadas) < 3 else 400
            return Conexao(eventos(n, base))

        with patch("urllib.request.urlopen", side_effect=fake):
            df = baixar_funding("BTCUSDT", 2400)

        assert len(chamadas) == 3, "deveria paginar em três requisições"
        assert len(df) <= 2400
        assert df["timestamp"].is_unique
        assert df["timestamp"].is_monotonic_increasing

    def test_simbolo_sem_perpetuo_da_mensagem_util(self):
        import urllib.error
        erro = urllib.error.HTTPError(
            "url", 400, "Bad Request", {},
            io.BytesIO(b'{"code":-1121,"msg":"Invalid symbol."}'))
        with patch("urllib.request.urlopen", side_effect=erro):
            with pytest.raises(FundingError) as exc:
                baixar_funding("EURUSD", 10)
        # A mensagem precisa dizer o que fazer, não só que falhou.
        assert "perpétuos" in str(exc.value)
        assert "BTCUSDT" in str(exc.value)

    def test_resposta_vazia_e_erro_explicito(self):
        with patch("urllib.request.urlopen") as mock:
            mock.return_value.__enter__.return_value = resposta([])
            with pytest.raises(FundingError):
                baixar_funding("BTCUSDT", 10)

    def test_pedido_zero_nao_chama_a_rede(self):
        with patch("urllib.request.urlopen") as mock:
            df = baixar_funding("BTCUSDT", 0)
        mock.assert_not_called()
        assert df.empty


class TestCarrego:
    """Aritmética, não previsão: precisa bater com a conta feita à mão."""

    def _df(self, taxas):
        return pd.DataFrame({
            "timestamp": pd.date_range(T0, periods=len(taxas), freq="8h", tz="UTC"),
            "rate": taxas,
        })

    def test_anualizacao_usa_1095_periodos(self):
        # 0,01% a cada 8h = 3 vezes ao dia = 1095 vezes ao ano
        r = rendimento_carry(self._df([0.0001] * 100))
        assert r["anualizado_pct"] == pytest.approx(10.95, abs=0.01)

    def test_acumulado_soma_as_taxas(self):
        r = rendimento_carry(self._df([0.0001] * 50))
        assert r["acumulado_pct"] == pytest.approx(0.5, abs=1e-9)

    def test_funding_negativo_inverte_o_sinal(self):
        r = rendimento_carry(self._df([-0.0002] * 30))
        assert r["anualizado_pct"] < 0
        assert r["positivos_pct"] == 0.0

    def test_conta_a_fracao_de_periodos_positivos(self):
        r = rendimento_carry(self._df([0.001] * 30 + [-0.001] * 10))
        assert r["positivos_pct"] == pytest.approx(75.0)

    def test_vazio_nao_quebra(self):
        assert rendimento_carry(pd.DataFrame()) == {}


class TestAlinhamento:
    """O erro mais caro do código antigo era olhar o futuro."""

    def _candles(self, n, preco_inicial=100.0, passo=0.0):
        precos = [preco_inicial + i * passo for i in range(n)]
        return pd.DataFrame({
            "timestamp": pd.date_range(T0, periods=n, freq="15min", tz="UTC"),
            "open": precos,
            "high": [p * 1.001 for p in precos],
            "low": [p * 0.999 for p in precos],
            "close": precos,
            "volume": 1.0,
        })

    def _funding(self, quando, taxa=0.0001):
        return pd.DataFrame({"timestamp": quando, "rate": [taxa] * len(quando)})

    def test_entra_no_candle_seguinte_ao_pagamento(self):
        """Nunca no candle que contém o instante do funding."""
        velas = self._candles(100, 100.0, 1.0)     # sobe 1 por candle
        # Pagamento exatamente no timestamp do candle de índice 10.
        quando = [velas["timestamp"].iloc[10]]
        dados = alinhar(self._funding(quando), velas, horizonte_horas=1)
        assert len(dados) == 1
        # Entrada é o OPEN do índice 11 (=111), não do 10 (=110).
        esperado_entrada = velas["open"].iloc[11]
        # 1 hora a partir da entrada (02:45) termina às 03:45, que é o
        # fechamento do candle de índice 14.
        esperado_saida = velas["close"].iloc[14]
        esperado = (esperado_saida / esperado_entrada - 1) * 100
        assert dados["retorno_pct"].iloc[0] == pytest.approx(esperado, rel=1e-9)

    def test_retorno_positivo_em_alta(self):
        dados = alinhar(self._funding([T0]), self._candles(50, 100.0, 1.0), 2)
        assert dados["retorno_pct"].iloc[0] > 0

    def test_retorno_negativo_em_queda(self):
        dados = alinhar(self._funding([T0]), self._candles(50, 200.0, -1.0), 2)
        assert dados["retorno_pct"].iloc[0] < 0

    def test_evento_sem_candles_suficientes_e_descartado(self):
        velas = self._candles(20)
        # Pagamento perto do fim: não há candles para completar o horizonte.
        quando = [velas["timestamp"].iloc[19]]
        assert alinhar(self._funding(quando), velas, horizonte_horas=8).empty

    def test_horizonte_maior_pega_mais_candles(self):
        velas = self._candles(200, 100.0, 0.5)
        curto = alinhar(self._funding([T0]), velas, 1)["retorno_pct"].iloc[0]
        longo = alinhar(self._funding([T0]), velas, 8)["retorno_pct"].iloc[0]
        assert longo > curto

    def test_entradas_vazias_devolvem_vazio(self):
        assert alinhar(pd.DataFrame(), self._candles(10), 8).empty
        assert alinhar(self._funding([T0]), pd.DataFrame(), 8).empty


def amostra(n, efeito, seed):
    """Dados sintéticos com relação plantada de tamanho conhecido.

    `efeito` = 0 significa funding e retorno independentes.
    """
    rng = np.random.default_rng(seed)
    rate = rng.normal(0.0001, 0.00012, n)
    z = (rate - rate.mean()) / rate.std()
    return pd.DataFrame({
        "timestamp": pd.date_range(T0, periods=n, freq="8h", tz="UTC"),
        "rate": rate,
        "retorno_pct": rng.normal(0, 1.2, n) - efeito * z,
    })


class TestEstatistica:
    """Detectar o que existe é metade; não inventar o que não existe é a outra."""

    def test_nao_inventa_efeito_onde_nao_ha(self):
        r = fs.teste_permutacao(amostra(800, 0.0, 3), permutacoes=1500, seed=3)
        assert r["p_value"] > 0.05

    def test_detecta_efeito_plantado(self):
        r = fs.teste_permutacao(amostra(800, 0.4, 3), permutacoes=1500, seed=3)
        assert r["p_value"] < 0.01
        assert r["spread_pct"] > 0

    def test_p_valor_nunca_e_zero(self):
        """Zero afirmaria certeza que 5000 sorteios não dão."""
        r = fs.teste_permutacao(amostra(800, 3.0, 5), permutacoes=500, seed=5)
        assert r["p_value"] > 0
        assert r["p_value"] == pytest.approx(round(1 / 501, 4), abs=1e-9)

    def test_quintis_ordenam_com_efeito_forte(self):
        grupos = por_quantil(amostra(1000, 0.6, 9), 5)
        retornos = [g["retorno_medio_pct"] for g in grupos]
        # funding cresce do grupo 1 ao 5; o retorno deve cair junto
        assert retornos == sorted(retornos, reverse=True)

    def test_quintis_nao_ordenam_sem_efeito(self):
        grupos = por_quantil(amostra(1000, 0.0, 9), 5)
        retornos = [g["retorno_medio_pct"] for g in grupos]
        assert retornos != sorted(retornos, reverse=True)

    def test_amostra_pequena_nao_produz_veredito(self):
        assert fs.teste_permutacao(amostra(10, 0.5, 1), permutacoes=100) == {}

    def test_grupos_somam_a_amostra(self):
        dados = amostra(500, 0.2, 2)
        assert sum(g["n"] for g in por_quantil(dados, 5)) == len(dados)

    def test_funding_constante_nao_forma_quantis(self):
        """Sem variação não há o que comparar."""
        dados = amostra(300, 0.0, 4)
        dados["rate"] = 0.0001
        assert por_quantil(dados, 5) == []


class TestHoldout:
    def test_divide_preservando_a_ordem_temporal(self):
        dados = amostra(100, 0.0, 1)
        treino, teste = dividir(dados, 0.3)
        assert len(treino) == 70 and len(teste) == 30
        assert treino["timestamp"].max() < teste["timestamp"].min()

    def test_fatia_de_teste_nao_aparece_no_treino(self):
        dados = amostra(100, 0.0, 1)
        treino, teste = dividir(dados, 0.25)
        assert set(treino["timestamp"]) & set(teste["timestamp"]) == set()

    def test_efeito_so_no_treino_nao_sobrevive(self):
        """Simula o caso que mais nos enganou: coincidência numa metade."""
        com_efeito = amostra(600, 0.5, 11)
        sem_efeito = amostra(600, 0.0, 12)
        sem_efeito["timestamp"] = pd.date_range(
            com_efeito["timestamp"].iloc[-1] + pd.Timedelta(hours=8),
            periods=600, freq="8h", tz="UTC")
        dados = pd.concat([com_efeito, sem_efeito], ignore_index=True)

        treino, teste = dividir(dados, 0.4)
        r_tr = fs.teste_permutacao(treino, permutacoes=1000, seed=1)
        r_te = fs.teste_permutacao(teste, permutacoes=1000, seed=2)
        assert r_tr["p_value"] < 0.05, "o efeito plantado deveria aparecer"
        assert r_te["p_value"] > 0.05, "e desaparecer onde não foi plantado"
