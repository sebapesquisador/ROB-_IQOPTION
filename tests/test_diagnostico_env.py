"""
Diagnóstico de origem da configuração.

Um .env editado que não surte efeito é falha silenciosa: nada dá erro, o
valor apenas continua o antigo. Aconteceu de verdade — três backtests
seguidos rodaram com timeframe 5 enquanto o .env dizia 15.
"""
import os

import pytest

from trading_bot.cli import _diagnostico_env


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestLocalizacaoDoArquivo:
    def test_encontra_env_na_pasta_atual(self, pasta, capsys):
        (pasta / ".env").write_text("TIMEFRAME_MINUTES=15\n")
        _diagnostico_env()
        out = capsys.readouterr().out
        assert "✔" in out
        assert ".env" in out

    def test_avisa_quando_nao_existe(self, pasta, capsys):
        _diagnostico_env()
        assert "NÃO existe" in capsys.readouterr().out

    def test_detecta_env_txt(self, pasta, capsys):
        """Extensão oculta do Windows: o arquivo vira .env.txt sem avisar."""
        (pasta / ".env.txt").write_text("TIMEFRAME_MINUTES=15\n")
        _diagnostico_env()
        out = capsys.readouterr().out
        assert ".env.txt" in out
        assert "renomeie para .env" in out

    def test_ignora_env_example(self, pasta, capsys):
        (pasta / ".env.example").write_text("TIMEFRAME_MINUTES=5\n")
        _diagnostico_env()
        out = capsys.readouterr().out
        assert "encontrados na pasta" not in out

    def test_aponta_env_em_pasta_acima(self, pasta, capsys, monkeypatch):
        """Rodar de uma subpasta é causa comum de o .env ser ignorado."""
        (pasta / ".env").write_text("TIMEFRAME_MINUTES=15\n")
        sub = pasta / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        _diagnostico_env()
        out = capsys.readouterr().out
        assert "existe um .env em" in out
        assert "rode o comando de dentro dessa pasta" in out


class TestVariaveisDeAmbiente:
    def test_avisa_sobre_precedencia(self, pasta, capsys, monkeypatch):
        (pasta / ".env").write_text("TIMEFRAME_MINUTES=15\n")
        monkeypatch.setenv("TIMEFRAME_MINUTES", "5")
        _diagnostico_env()
        out = capsys.readouterr().out
        assert "têm prioridade sobre o .env" in out
        assert "TIMEFRAME_MINUTES=5" in out

    def test_ensina_a_limpar_no_powershell(self, pasta, capsys, monkeypatch):
        monkeypatch.setenv("BROKER", "paper")
        _diagnostico_env()
        assert "Remove-Item Env:\\BROKER" in capsys.readouterr().out

    def test_silencioso_sem_variaveis(self, pasta, capsys, monkeypatch):
        for k in ("TIMEFRAME_MINUTES", "EXPIRATION_MINUTES", "BROKER",
                  "DRY_RUN", "SYMBOL", "ACCOUNT_MODE"):
            monkeypatch.delenv(k, raising=False)
        (pasta / ".env").write_text("TIMEFRAME_MINUTES=15\n")
        _diagnostico_env()
        assert "prioridade" not in capsys.readouterr().out
