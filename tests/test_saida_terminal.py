"""Saída em terminais que não falam UTF-8.

Bug real: `python -m trading_bot.cli backtest-spot ... | Tee-Object saida.txt`
derrubava o programa no Windows. Ao escrever no console o Python usa UTF-8,
mas ao ser redirecionado usa a codificação local (cp1252), e uma seta comum
vira UnicodeEncodeError. Pior: o tratador de erro quebrava de novo ao tentar
imprimir "✖".

Nada disso aparece em terminal UTF-8 — por isso os testes forçam a
codificação, em vez de confiar no ambiente.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

import trading_bot
from trading_bot.cli import (_SUBSTITUTOS, _ajustar_saida_para_o_terminal,
                             _instalar_traducao)

RAIZ = str(Path(trading_bot.__file__).resolve().parent.parent)


class TestTraducaoDeSimbolos:
    def test_troca_apenas_o_que_falta_na_codificacao(self):
        fake = io.StringIO()
        _instalar_traducao(fake, {ord("→"): "->"})
        fake.write("candles 100 → 200, ação cara")
        # A seta foi trocada; o acento, que a cp1252 tem, ficou intacto.
        assert fake.getvalue() == "candles 100 -> 200, ação cara"

    def test_todo_substituto_cabe_em_ascii(self):
        """De nada adianta trocar um símbolo exótico por outro."""
        for simbolo, alternativa in _SUBSTITUTOS.items():
            alternativa.encode("ascii")     # levanta se não couber

    def test_substitutos_cobrem_os_simbolos_que_o_relatorio_usa(self):
        usados = ["→", "←", "✔", "✖", "⚠"]
        for s in usados:
            assert s in _SUBSTITUTOS, f"{s} aparece na saída e não tem alternativa"

    def test_nao_mexe_em_terminal_utf8(self):
        """Quem tem UTF-8 merece os símbolos de verdade."""
        original_out, original_err = sys.stdout, sys.stderr
        buffer = io.BytesIO()
        try:
            sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8")
            sys.stderr = sys.stdout
            _ajustar_saida_para_o_terminal()
            sys.stdout.write("100 → 200 ✔")
            sys.stdout.flush()
            escrito = buffer.getvalue()   # antes do GC fechar o buffer
        finally:
            sys.stdout, sys.stderr = original_out, original_err
        assert escrito.decode("utf-8") == "100 → 200 ✔"


@pytest.mark.parametrize("codificacao", ["cp1252", "ascii", "latin-1"])
class TestProgramaCompleto:
    """Roda o CLI de verdade, num processo com a codificação limitada."""

    def _rodar(self, args, codificacao, extra_env=None):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = codificacao
        env["BROKER"] = "paper"
        env["PYTHONPATH"] = RAIZ + os.pathsep + env.get("PYTHONPATH", "")
        env.update(extra_env or {})
        # Sem text=True: o filho escreve bytes na codificação limitada, e
        # decodificá-los como UTF-8 seria só trocar de erro de lugar.
        bruto = subprocess.run(
            [sys.executable, "-m", "trading_bot.cli", *args],
            capture_output=True, env=env, timeout=300, cwd=RAIZ,
        )

        class Saida:
            returncode = bruto.returncode
            stdout = bruto.stdout.decode(codificacao, "replace")
            stderr = bruto.stderr.decode(codificacao, "replace")
        return Saida

    def test_backtest_spot_nao_quebra(self, codificacao):
        r = self._rodar(["backtest-spot", "--candles", "600"], codificacao)
        assert "UnicodeEncodeError" not in r.stderr
        assert r.returncode == 0

    def test_validate_nao_quebra(self, codificacao):
        r = self._rodar(["validate"], codificacao)
        assert "UnicodeEncodeError" not in r.stderr
        assert r.returncode == 0

    def test_erro_esperado_nao_vira_crash(self, codificacao):
        """O aviso de erro jamais pode ser a segunda causa de falha."""
        r = self._rodar(["backtest-spot", "--candles", "100"], codificacao,
                        {"BROKER": "binance", "SYMBOL": "EURUSD"})
        assert "UnicodeEncodeError" not in r.stderr
        assert r.returncode == 1
        assert "EURUSD" in r.stdout

    def test_texto_em_portugues_sobrevive(self, codificacao):
        """Trocar símbolo é aceitável; perder o texto não é."""
        r = self._rodar(["strategies"], codificacao)
        assert "UnicodeEncodeError" not in r.stderr
        assert "bollinger_reversion" in r.stdout


class TestCodificacaoDoConsole:
    """Descoberta da página de código que o console realmente usa.

    A primeira correção não travava mais, mas entregava "estratÚgia": o
    Python escrevia em cp1252 (ANSI do sistema) e o PowerShell lia em cp850
    (OEM do console). As duas diferem exatamente nos acentos.
    """

    def test_fora_do_windows_nao_interfere(self, monkeypatch):
        from trading_bot.cli import _codificacao_do_console
        monkeypatch.setattr(sys, "platform", "linux")
        assert _codificacao_do_console() is None

    def test_reproduz_o_erro_relatado(self):
        """cp1252 escrito, cp850 lido: é assim que "é" vira "Ú"."""
        assert "estratégia".encode("cp1252").decode("cp850") == "estratÚgia"
        # Escrever na codificação certa resolve.
        assert "estratégia".encode("cp850").decode("cp850") == "estratégia"

    def test_utf8_nao_salvaria(self):
        """Prova de que forçar UTF-8 seria a correção errada."""
        bagunca = "estratégia".encode("utf-8").decode("cp850")
        assert bagunca != "estratégia"

    def test_windows_usa_a_pagina_do_console(self, monkeypatch):
        from trading_bot import cli
        monkeypatch.setattr(sys, "platform", "win32")

        class FakeKernel:
            @staticmethod
            def GetConsoleOutputCP():
                return 850

        fake = type("W", (), {"kernel32": FakeKernel})()
        monkeypatch.setitem(sys.modules, "ctypes",
                            type("C", (), {"windll": fake}))
        assert cli._codificacao_do_console() == "cp850"

    def test_console_em_utf8_e_reconhecido(self, monkeypatch):
        from trading_bot import cli
        monkeypatch.setattr(sys, "platform", "win32")

        class FakeKernel:
            @staticmethod
            def GetConsoleOutputCP():
                return 65001

        fake = type("W", (), {"kernel32": FakeKernel})()
        monkeypatch.setitem(sys.modules, "ctypes",
                            type("C", (), {"windll": fake}))
        assert cli._codificacao_do_console() == "utf-8"

    def test_pagina_desconhecida_nao_quebra(self, monkeypatch):
        from trading_bot import cli
        monkeypatch.setattr(sys, "platform", "win32")

        class FakeKernel:
            @staticmethod
            def GetConsoleOutputCP():
                return 99999

        fake = type("W", (), {"kernel32": FakeKernel})()
        monkeypatch.setitem(sys.modules, "ctypes",
                            type("C", (), {"windll": fake}))
        assert cli._codificacao_do_console() is None
