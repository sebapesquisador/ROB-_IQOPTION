"""
Testes do adaptador Binance.

Cobrem decisões que afetam diretamente a validade do backtest e a segurança
da conta: origem dos dados históricos, credenciais de exemplo não
substituídas e envio de ordens sem credencial.
"""
from unittest.mock import patch

import pytest

from trading_bot.brokers.base import ConnectionError_
from trading_bot.brokers.binance import BinanceBroker
from trading_bot.core.config import Broker as B, Settings
from trading_bot.core.models import Direction, OrderStatus


MS_15M = 900_000
BASE_MS = 1_700_000_000_000


def make_settings(**kw):
    base = dict(broker=B.BINANCE, dry_run=True, symbol="BTCUSDT")
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def broker():
    b = BinanceBroker(make_settings())
    b.connect()
    return b


class TestCredenciais:
    @pytest.mark.parametrize("key,secret", [
        ("sua_chave", "seu_segredo"),
        ("SUA_CHAVE", "SEU_SEGREDO"),
        ("your_api_key", "your_api_secret"),
        ("cole_sua_testnet_api_key_aqui", "cole_sua_testnet_secret_key_aqui"),
    ])
    def test_recusa_valores_de_exemplo(self, key, secret):
        """Copiar o .env.example sem substituir é erro silencioso comum."""
        b = BinanceBroker(make_settings(binance_api_key=key, binance_api_secret=secret))
        with pytest.raises(ConnectionError_, match="valor de exemplo"):
            b.connect()

    def test_sem_chaves_conecta_somente_leitura(self):
        """Candles são públicos: backtest não deve exigir credencial."""
        b = BinanceBroker(make_settings())
        assert b.connect() is True
        assert b._read_only is True

    def test_somente_leitura_recusa_ordem(self, broker):
        o = broker.place_order("BTCUSDT", Direction.CALL, 10.0, 5)
        assert o.status is OrderStatus.REJECTED
        assert "somente leitura" in o.reason

    def test_sem_client_recusa_ordem(self):
        """Proteção extra: nunca chamar a API sem cliente inicializado."""
        b = BinanceBroker(make_settings())
        b._read_only = False
        b.client = None
        o = b.place_order("BTCUSDT", Direction.CALL, 10.0, 5)
        assert o.status is OrderStatus.REJECTED


class TestOrigemDosDados:
    def test_klines_vem_da_mainnet_mesmo_com_testnet_ligada(self):
        """
        O histórico da testnet é gerado por um motor de testes com liquidez
        artificial. Backtestar sobre ele mede ficção, então os candles saem
        sempre do endpoint público da mainnet.
        """
        b = BinanceBroker(make_settings(binance_testnet=True))
        assert "api.binance.com" in b._PUBLIC_KLINES
        assert "testnet" not in b._PUBLIC_KLINES


class TestPaginacao:
    def _fake(self, chamadas):
        def fn(_self, symbol, interval, limit, end_ms=None):
            chamadas.append((limit, end_ms))
            fim = end_ms if end_ms is not None else BASE_MS + 3000 * MS_15M
            inicio = fim - limit * MS_15M
            return [[inicio + i * MS_15M, "100", "102", "99", "101", "5",
                     0, 0, 0, 0, 0, 0] for i in range(limit)]
        return fn

    def test_entrega_o_total_pedido(self, broker):
        chamadas = []
        with patch.object(BinanceBroker, "_fetch_klines_publico", self._fake(chamadas)):
            df = broker.get_candles("BTCUSDT", 15, 2500)
        assert len(df) == 2500

    def test_encadeia_requisicoes(self, broker):
        chamadas = []
        with patch.object(BinanceBroker, "_fetch_klines_publico", self._fake(chamadas)):
            broker.get_candles("BTCUSDT", 15, 2500)
        assert [c[0] for c in chamadas] == [1000, 1000, 500]

    def test_uma_chamada_quando_cabe(self, broker):
        chamadas = []
        with patch.object(BinanceBroker, "_fetch_klines_publico", self._fake(chamadas)):
            broker.get_candles("BTCUSDT", 15, 400)
        assert len(chamadas) == 1

    def test_sem_duplicatas_e_ordenado(self, broker):
        chamadas = []
        with patch.object(BinanceBroker, "_fetch_klines_publico", self._fake(chamadas)):
            df = broker.get_candles("BTCUSDT", 15, 2500)
        assert df["timestamp"].duplicated().sum() == 0
        assert df["timestamp"].is_monotonic_increasing

    def test_para_quando_historico_acaba(self, broker):
        """Lote menor que o pedido significa fim do histórico."""
        def curto(_self, symbol, interval, limit, end_ms=None):
            return [[BASE_MS + i * MS_15M, "100", "102", "99", "101", "5",
                     0, 0, 0, 0, 0, 0] for i in range(min(limit, 120))]
        with patch.object(BinanceBroker, "_fetch_klines_publico", curto):
            df = broker.get_candles("BTCUSDT", 15, 5000)
        assert len(df) == 120

    def test_timeframe_invalido_orienta(self, broker):
        from trading_bot.brokers.base import BrokerError
        with pytest.raises(BrokerError, match="não suportado"):
            broker.get_candles("BTCUSDT", 7, 100)
