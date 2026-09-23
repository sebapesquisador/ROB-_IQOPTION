"""
Seleção de porta do painel.

Porta 8000 ocupada por outro programa é situação comum. O uvicorn falhava
com "error while attempting to bind on address", sem indicar a saída.
"""
import socket

import pytest

from trading_bot.cli import _port_livre, cmd_dashboard


@pytest.fixture
def porta_ocupada():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    yield s.getsockname()[1]
    s.close()


class Args:
    host = "127.0.0.1"
    port = None
    reload = False


class TestDeteccao:
    def test_detecta_ocupada(self, porta_ocupada):
        assert _port_livre("127.0.0.1", porta_ocupada) is False

    def test_detecta_livre(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        assert _port_livre("127.0.0.1", p) is True

    def test_0000_e_testado_via_loopback(self, porta_ocupada):
        """Bind em 0.0.0.0 não é sondável direto; usa 127.0.0.1."""
        assert _port_livre("0.0.0.0", porta_ocupada) is False


class TestComportamento:
    def test_porta_explicita_ocupada_falha_com_sugestao(self, porta_ocupada, capsys,
                                                        monkeypatch):
        """Pedido explícito não é trocado em silêncio."""
        monkeypatch.setattr("trading_bot.cli._banner", lambda *a: None)

        class A(Args):
            port = porta_ocupada

        assert cmd_dashboard(A()) == 1
        out = capsys.readouterr().out
        assert "já está em uso" in out
        assert "Sugestão" in out

    def test_porta_padrao_ocupada_migra(self, porta_ocupada, capsys, monkeypatch):
        """Sem --port, encontra a próxima livre e avisa em vez de abortar."""
        monkeypatch.setattr("trading_bot.cli._banner", lambda *a: None)
        usados = {}

        def fake_run(app, **kw):
            usados.update(kw)

        monkeypatch.setattr("uvicorn.run", fake_run)

        settings = __import__("trading_bot.cli", fromlist=["get_settings"]).get_settings()
        monkeypatch.setattr(settings, "api_port", porta_ocupada, raising=False)
        monkeypatch.setattr(settings, "api_host", "127.0.0.1", raising=False)
        monkeypatch.setattr("trading_bot.cli.get_settings", lambda: settings)

        assert cmd_dashboard(Args()) == 0
        assert usados["port"] != porta_ocupada
        assert "ocupada" in capsys.readouterr().out

    def test_url_usa_localhost_e_nao_0000(self, capsys, monkeypatch):
        """0.0.0.0 não é endereço navegável."""
        monkeypatch.setattr("trading_bot.cli._banner", lambda *a: None)
        monkeypatch.setattr("uvicorn.run", lambda app, **kw: None)

        settings = __import__("trading_bot.cli", fromlist=["get_settings"]).get_settings()
        monkeypatch.setattr(settings, "api_host", "0.0.0.0", raising=False)
        monkeypatch.setattr("trading_bot.cli.get_settings", lambda: settings)

        class A(Args):
            host = None   # sem --host: cai no api_host 0.0.0.0

        cmd_dashboard(A())
        out = capsys.readouterr().out
        assert "http://localhost:" in out
        assert "http://0.0.0.0:" not in out
