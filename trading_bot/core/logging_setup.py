"""
Configuração de logging.

O projeto original usava logging.basicConfig no topo de dois módulos
diferentes, escrevendo em arquivos que cresciam sem limite e imprimindo
emojis em toda linha. Aqui: rotação de arquivo, formato limpo no console
e opção de saída JSON para ingestão em ferramentas de observabilidade.

Importante: NUNCA logar credenciais. O filtro abaixo mascara padrões
sensíveis por segurança, caso algo escape.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import re
import sys
from pathlib import Path

_SENSITIVE = re.compile(
    r"(password|senha|secret|api[_-]?key|token)[\"'\s:=]+([^\s,\"'}]+)", re.IGNORECASE
)


class RedactFilter(logging.Filter):
    """Mascara segredos que por acidente cheguem ao log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE.sub(r"\1=***", record.msg)
        return True


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m", "INFO": "\033[32m",
        "WARNING": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = use_color and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        level = record.levelname
        name = record.name.replace("trading_bot.", "")
        if self.use_color:
            color = self.COLORS.get(level, "")
            level = f"{color}{level:<7}{self.RESET}"
        else:
            level = f"{level:<7}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts} {level} {name:<22} {msg}"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", log_file: Path | None = None,
                  json_output: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    redact = RedactFilter()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(JSONFormatter() if json_output else ConsoleFormatter())
    console.addFilter(redact)
    root.addHandler(console)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Rotação: 10MB por arquivo, 5 arquivos — o log antigo crescia sem limite
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(JSONFormatter() if json_output else logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)-24s %(message)s"
        ))
        fh.addFilter(redact)
        root.addHandler(fh)

    # Silencia bibliotecas verbosas
    for noisy in ("websocket", "urllib3", "requests", "iqoptionapi", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
