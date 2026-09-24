"""Compatibilidade entre ativo e corretora.

Nasceu de um caso real: `BROKER=binance` com `SYMBOL=EURUSD` (herdado da
configuração de IQ Option) passava na validação, conectava, e só falhava na
hora de baixar candles. O erro precisa aparecer antes disso.
"""
from __future__ import annotations

import pytest

from trading_bot.core.config import Broker, checar_simbolo


class TestBinance:
    @pytest.mark.parametrize("par", [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "ETHBTC", "BNBETH",
        "BTCBRL", "ADAEUR", "btcusdt",
    ])
    def test_pares_validos_passam(self, par):
        assert checar_simbolo(Broker.BINANCE, par) is None

    @pytest.mark.parametrize("par", [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "eurusd",
    ])
    def test_forex_e_recusado(self, par):
        msg = checar_simbolo(Broker.BINANCE, par)
        assert msg is not None
        assert "Forex" in msg or "câmbio" in msg
        # A mensagem precisa dizer o que fazer, não só o que está errado.
        assert "BTCUSDT" in msg

    def test_separador_e_apontado_com_a_forma_correta(self):
        msg = checar_simbolo(Broker.BINANCE, "BTC/USDT")
        assert msg is not None
        assert "BTCUSDT" in msg

    def test_quote_desconhecida_avisa(self):
        msg = checar_simbolo(Broker.BINANCE, "BTCXYZ")
        assert msg is not None
        assert "cotação" in msg

    def test_par_de_otc_da_iq_nao_passa(self):
        # EURUSD-OTC vira EURUSDOTC ao limpar: não é Forex puro nem tem
        # quote conhecida, mas precisa ser barrado de algum jeito.
        assert checar_simbolo(Broker.BINANCE, "EURUSD-OTC") is not None


class TestIQOption:
    @pytest.mark.parametrize("par", ["EURUSD", "EURUSD-OTC", "GBPJPY"])
    def test_pares_de_cambio_passam(self, par):
        assert checar_simbolo(Broker.IQOPTION, par) is None

    def test_par_de_cripto_da_binance_avisa(self):
        msg = checar_simbolo(Broker.IQOPTION, "BTCUSDT")
        assert msg is not None
        assert "EURUSD" in msg


class TestNeutro:
    def test_paper_aceita_qualquer_coisa(self):
        # O broker paper gera série sintética; o nome é só um rótulo.
        assert checar_simbolo(Broker.PAPER, "EURUSD") is None
        assert checar_simbolo(Broker.PAPER, "BTCUSDT") is None

    @pytest.mark.parametrize("vazio", ["", "   ", None])
    def test_vazio_nao_quebra(self, vazio):
        assert checar_simbolo(Broker.BINANCE, vazio) is None
