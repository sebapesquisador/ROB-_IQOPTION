"""
Testes de regressão do adaptador IQ Option.

Cobrem falhas reais encontradas em uso: a biblioteca `iqoptionapi` quebra
com `TypeError: 'NoneType' object is not subscriptable` ao listar ativos
quando a corretora demora a responder. O robô não pode cair junto.
"""
from __future__ import annotations

import pytest

from trading_bot.brokers.base import BrokerError
from trading_bot.brokers.iqoption import IQOptionBroker
from trading_bot.core.config import Broker as B, Settings


def make_settings(**kw) -> Settings:
    base = dict(broker=B.IQOPTION, dry_run=True, symbol="EURUSD", auto_otc=True)
    base.update(kw)
    return Settings(**base)


def candles(n: int, tf: int = 300) -> list[dict]:
    import time
    t0 = int(time.time()) - n * tf
    return [
        {"from": t0 + i * tf, "open": 1.1, "close": 1.1005,
         "min": 1.0995, "max": 1.1010, "volume": 10}
        for i in range(n)
    ]


class FakeAPI:
    """API configurável para reproduzir cada modo de falha."""

    def __init__(self, *, init_v2=None, open_time=None, raise_open_time=False,
                 candles_for=None):
        self._init_v2 = init_v2
        self._open_time = open_time or {}
        self._raise = raise_open_time
        self._candles_for = candles_for or {}
        self.calls: list[str] = []

    def get_all_init_v2(self):
        return self._init_v2

    def get_all_open_time(self):
        if self._raise:
            raise TypeError("'NoneType' object is not subscriptable")
        return self._open_time

    def get_candles(self, symbol, tf, count, end):
        self.calls.append(symbol)
        data = self._candles_for.get(symbol)
        return data(count) if callable(data) else data


@pytest.fixture
def broker() -> IQOptionBroker:
    b = IQOptionBroker(make_settings())
    b._connected = True
    return b


class TestListagemDeAtivosResiliente:
    def test_nao_propaga_erro_da_biblioteca(self, broker):
        """O TypeError da iqoptionapi não pode derrubar o robô."""
        broker.api = FakeAPI(raise_open_time=True)
        assert broker._open_assets() == {}          # degrada, não explode

    def test_usa_init_v2_quando_disponivel(self, broker):
        broker.api = FakeAPI(init_v2={
            "binary": {"actives": {
                "1": {"name": "front.EURUSD", "enabled": True, "is_suspended": False},
                "2": {"name": "front.GBPUSD", "enabled": True, "is_suspended": True},
            }},
        })
        assert broker._is_open("EURUSD", "binary") is True
        assert broker._is_open("GBPUSD", "binary") is False   # suspenso

    def test_cai_para_legacy_se_v2_vazio(self, broker):
        broker.api = FakeAPI(
            init_v2=None,
            open_time={"binary": {"EURUSD": {"open": True}}},
        )
        assert broker._is_open("EURUSD", "binary") is True

    def test_availability_known(self, broker):
        broker.api = FakeAPI(raise_open_time=True)
        broker._open_assets()
        assert broker._availability_known() is False


class TestResolucaoDeSimbolo:
    def test_sem_lista_nao_devolve_par_fechado(self, broker, monkeypatch):
        """Com a lista indisponível e FOREX fechado, deve escolher OTC."""
        broker.api = FakeAPI(raise_open_time=True)
        monkeypatch.setattr(IQOptionBroker, "_forex_open_now", staticmethod(lambda: False))
        assert broker.resolve_symbol("EURUSD") == "EURUSD-OTC"

    def test_sem_lista_com_forex_aberto_usa_par_normal(self, broker, monkeypatch):
        broker.api = FakeAPI(raise_open_time=True)
        monkeypatch.setattr(IQOptionBroker, "_forex_open_now", staticmethod(lambda: True))
        assert broker.resolve_symbol("EURUSD") == "EURUSD"

    def test_prefere_par_normal_quando_aberto(self, broker):
        broker.api = FakeAPI(open_time={"binary": {"EURUSD": {"open": True}}})
        assert broker.resolve_symbol("EURUSD") == "EURUSD"

    def test_cai_para_otc_quando_normal_fechado(self, broker):
        broker.api = FakeAPI(open_time={"binary": {
            "EURUSD": {"open": False}, "EURUSD-OTC": {"open": True},
        }})
        assert broker.resolve_symbol("EURUSD") == "EURUSD-OTC"

    def test_is_tradable_permissivo_sem_lista(self, broker):
        """Sem informação, deixa a corretora decidir — não bloqueia por suposição."""
        broker.api = FakeAPI(raise_open_time=True)
        assert broker.is_tradable("EURUSD") is True


class TestObtencaoDeCandles:
    def test_fallback_automatico_para_otc(self, broker):
        broker.api = FakeAPI(
            raise_open_time=True,
            candles_for={"EURUSD": lambda n: None, "EURUSD-OTC": candles},
        )
        df = broker.get_candles("EURUSD", 5, 150)
        assert len(df) == 150
        assert "EURUSD-OTC" in broker.api.calls

    def test_retry_antes_de_desistir(self, broker):
        """Falha intermitente não pode derrubar o ciclo."""
        state = {"n": 0}

        def flaky(count):
            state["n"] += 1
            return candles(count) if state["n"] >= 2 else None

        broker.api = FakeAPI(raise_open_time=True, candles_for={"EURUSD": flaky})
        df = broker.get_candles("EURUSD", 5, 120)
        assert len(df) == 120
        assert state["n"] >= 2

    def test_erro_claro_quando_nada_funciona(self, broker):
        broker.api = FakeAPI(
            raise_open_time=True,
            candles_for={"EURUSD": lambda n: None, "EURUSD-OTC": lambda n: None},
        )
        with pytest.raises(BrokerError) as exc:
            broker.get_candles("EURUSD", 5, 100)
        assert "mercado está aberto" in str(exc.value)

    def test_candles_normalizados(self, broker):
        broker.api = FakeAPI(raise_open_time=True, candles_for={"EURUSD": candles})
        df = broker.get_candles("EURUSD", 5, 100)
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert df["timestamp"].is_monotonic_increasing
        assert (df["high"] >= df["low"]).all()


class TestCalendarioForex:
    @pytest.mark.parametrize("weekday,hour,expected", [
        (5, 12, False),   # sábado
        (6, 10, False),   # domingo de manhã
        (6, 22, True),    # domingo após abertura
        (4, 22, False),   # sexta após fechamento
        (2, 14, True),    # quarta no pregão
    ])
    def test_janela(self, monkeypatch, weekday, hour, expected):
        from datetime import datetime, timezone

        class FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                # 2024-01-01 é segunda: soma o offset do dia desejado
                return datetime(2024, 1, 1 + weekday, hour, 0, tzinfo=timezone.utc)

        monkeypatch.setattr("trading_bot.brokers.iqoption.datetime", FakeDT)
        assert IQOptionBroker._forex_open_now() is expected


class TestPaginacao:
    """
    Regressão: a versão anterior truncava com min(count, 1000). Quem pedia
    3000 candles recebia 1000 sem aviso, e o backtest rodava sobre um terço
    da amostra — produzindo o veredito "amostra insuficiente" sem que o
    usuário entendesse a causa.
    """

    class PagedAPI:
        TF = 300

        def __init__(self, historico: int = 5000):
            import time as _t
            self.calls: list[tuple[int, int]] = []
            self.historico = historico
            # Ancorado no relógio real, pois o broker pagina a partir de time.time()
            self.base = int(_t.time()) // self.TF * self.TF

        def get_all_init_v2(self):
            return None

        def get_all_open_time(self):
            return {}

        def get_candles(self, symbol, tf, n, end):
            self.calls.append((n, int(end)))
            n = min(n, 1000)  # teto real da API
            end_slot = int(end) // tf * tf
            out = []
            for i in range(n):
                ts = end_slot - i * tf
                if ts < self.base - self.historico * tf:
                    break
                out.append({"from": ts, "open": 1.1, "close": 1.1,
                            "min": 1.09, "max": 1.11, "volume": 1})
            return list(reversed(out))

    @pytest.fixture
    def paged(self):
        b = IQOptionBroker(make_settings(auto_otc=False))
        b.api = self.PagedAPI()
        b._connected = True
        return b

    def test_entrega_o_total_pedido(self, paged):
        df = paged.get_candles("EURUSD", 5, 3000)
        assert len(df) == 3000

    def test_faz_multiplas_chamadas(self, paged):
        paged.get_candles("EURUSD", 5, 3000)
        assert len(paged.api.calls) >= 3   # 1000 por chamada

    def test_uma_chamada_quando_cabe(self, paged):
        paged.get_candles("EURUSD", 5, 500)
        assert len(paged.api.calls) == 1

    def test_sem_duplicatas_entre_paginas(self, paged):
        df = paged.get_candles("EURUSD", 5, 2500)
        assert df["timestamp"].duplicated().sum() == 0

    def test_ordem_cronologica(self, paged):
        df = paged.get_candles("EURUSD", 5, 2500)
        assert df["timestamp"].is_monotonic_increasing

    def test_para_quando_historico_acaba(self):
        b = IQOptionBroker(make_settings(auto_otc=False))
        b.api = self.PagedAPI(historico=1500)
        b._connected = True
        df = b.get_candles("EURUSD", 5, 9000)
        assert 0 < len(df) <= 1501        # devolve o que existe
        assert len(b.api.calls) < 20      # não entra em laço infinito
