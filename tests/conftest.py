"""
Isolamento dos testes.

Sem isto, a suíte lê o `.env` real do desenvolvedor e os testes passam ou
falham conforme a configuração local da máquina — exatamente o tipo de
falso negativo que faz uma equipe perder confiança nos testes.

A estratégia: rodar cada teste a partir de um diretório temporário (o
`env_file=".env"` é relativo ao cwd) e limpar as variáveis de ambiente
do projeto.
"""
from __future__ import annotations

import os
import pytest

_PREFIXES = ("RISK_", "STRAT_", "SESSION_")
_KEYS = (
    "BROKER", "ACCOUNT_MODE", "DRY_RUN", "SYMBOL", "TIMEFRAME_MINUTES",
    "EXPIRATION_MINUTES", "AUTO_OTC", "CANDLES_LOOKBACK", "POLL_INTERVAL_SECONDS",
    "IQ_EMAIL", "IQ_PASSWORD", "BINANCE_API_KEY", "BINANCE_API_SECRET",
    "BINANCE_TESTNET", "API_HOST", "API_PORT", "API_TOKEN",
    "DATABASE_URL", "LOG_LEVEL", "LOG_JSON",
)


@pytest.fixture(autouse=True)
def isolate_environment(tmp_path, monkeypatch):
    """Cada teste roda com configuração limpa e determinística."""
    for key in list(os.environ):
        if key in _KEYS or key.startswith(_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)  # impede a leitura do .env do projeto
    yield
