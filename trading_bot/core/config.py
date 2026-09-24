"""
Configuração central tipada e validada.

Toda credencial vem de variáveis de ambiente / arquivo .env.
Nada de segredo hardcoded no código-fonte.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"


class Broker(str, Enum):
    IQOPTION = "iqoption"
    BINANCE = "binance"
    PAPER = "paper"


class AccountMode(str, Enum):
    DEMO = "demo"
    REAL = "real"


class RiskConfig(BaseSettings):
    """Gestão de risco. É a camada que impede o robô de quebrar a conta."""

    model_config = SettingsConfigDict(env_prefix="RISK_", env_file=".env", extra="ignore")

    # Dimensionamento de posição
    sizing_mode: Literal["fixed", "percent"] = "percent"
    fixed_stake: float = Field(default=5.0, gt=0, description="Valor fixo por operação")
    percent_stake: float = Field(
        default=1.0, gt=0, le=5.0, description="% do saldo por operação (máx. 5%)"
    )

    # Limites de perda — travas obrigatórias
    max_daily_loss_pct: float = Field(
        default=5.0, gt=0, le=50.0, description="Perda máxima diária em % do saldo inicial do dia"
    )
    max_total_drawdown_pct: float = Field(
        default=20.0, gt=0, le=90.0, description="Drawdown máximo sobre o pico de equity"
    )
    max_consecutive_losses: int = Field(
        default=5, ge=1, description="Pausa o robô após N derrotas seguidas"
    )
    cooldown_after_loss_streak_min: int = Field(
        default=30, ge=0, description="Minutos de pausa após atingir o limite de derrotas"
    )

    # Metas
    daily_profit_target_pct: float = Field(
        default=5.0, gt=0, description="Meta diária em % — para o robô ao atingir"
    )

    # Limites operacionais
    max_trades_per_day: int = Field(default=50, ge=1)
    max_concurrent_positions: int = Field(default=1, ge=1)
    min_seconds_between_trades: int = Field(default=30, ge=0)

    # Martingale — desabilitado por padrão, é um destruidor de contas
    martingale_enabled: bool = False
    martingale_multiplier: float = Field(default=2.0, ge=1.0, le=3.0)
    martingale_max_steps: int = Field(default=2, ge=0, le=3)

    @model_validator(mode="after")
    def _validate_coherence(self) -> "RiskConfig":
        if self.martingale_enabled and self.martingale_max_steps == 0:
            raise ValueError("martingale_enabled=True exige martingale_max_steps >= 1")
        return self


class StrategyConfig(BaseSettings):
    """Parâmetros de indicadores, compartilhados por todas as estratégias."""

    model_config = SettingsConfigDict(env_prefix="STRAT_", env_file=".env", extra="ignore")

    name: str = "rsi_reversal"

    # RSI
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_oversold: float = Field(default=30.0, ge=1, le=49)
    rsi_overbought: float = Field(default=70.0, ge=51, le=99)

    # Médias móveis
    ma_fast_period: int = Field(default=9, ge=2, le=200)
    ma_slow_period: int = Field(default=21, ge=3, le=400)
    ma_type: Literal["EMA", "SMA"] = "EMA"

    # Bandas de Bollinger
    bb_period: int = Field(default=20, ge=5, le=100)
    bb_std: float = Field(default=2.0, gt=0.5, le=4.0)

    # MACD
    macd_fast: int = Field(default=12, ge=2)
    macd_slow: int = Field(default=26, ge=3)
    macd_signal: int = Field(default=9, ge=2)

    # Williams %R — oscilador de -100 (fundo da faixa) a 0 (topo)
    #
    # Os quatro níveis são independentes de propósito: entrada e saída não
    # precisam ser simétricas, e o intervalo entre elas é o que define se a
    # estratégia segura a posição ou gira rápido. Todos ajustáveis no .env
    # com o prefixo STRAT_.
    wpr_period: int = Field(default=20, ge=2, le=200)
    wpr_buy: float = Field(
        default=-95.0, ge=-100, le=0,
        description="Compra quando o WPR fica ABAIXO deste nível")
    wpr_sell: float = Field(
        default=-5.0, ge=-100, le=0,
        description="Vende quando o WPR fica ACIMA deste nível")
    wpr_exit_buy: float = Field(
        default=-20.0, ge=-100, le=0,
        description="Encerra a compra quando o WPR passa ACIMA deste nível")
    wpr_exit_sell: float = Field(
        default=-80.0, ge=-100, le=0,
        description="Encerra a venda quando o WPR cai ABAIXO deste nível")

    @model_validator(mode="after")
    def _checar_niveis_wpr(self):
        """Impede combinações que travariam a estratégia em silêncio.

        Sem isso, trocar um número no .env pode produzir uma estratégia que
        abre e fecha no mesmo candle — ou que nunca fecha — sem nenhum erro
        visível. Melhor recusar a configuração do que operar assim.
        """
        if self.wpr_exit_buy <= self.wpr_buy:
            raise ValueError(
                f"STRAT_WPR_EXIT_BUY ({self.wpr_exit_buy}) precisa ser MAIOR que "
                f"STRAT_WPR_BUY ({self.wpr_buy}): compra-se no fundo da faixa e "
                f"sai-se mais acima. Do jeito atual a compra sairia no mesmo "
                f"instante em que entrasse."
            )
        if self.wpr_exit_sell >= self.wpr_sell:
            raise ValueError(
                f"STRAT_WPR_EXIT_SELL ({self.wpr_exit_sell}) precisa ser MENOR que "
                f"STRAT_WPR_SELL ({self.wpr_sell}): vende-se no topo da faixa e "
                f"sai-se mais abaixo."
            )
        if self.wpr_buy >= self.wpr_sell:
            raise ValueError(
                f"STRAT_WPR_BUY ({self.wpr_buy}) precisa ser MENOR que "
                f"STRAT_WPR_SELL ({self.wpr_sell}) — senão o mesmo candle "
                f"dispara compra e venda ao mesmo tempo."
            )
        return self

    # ATR — usado como filtro de volatilidade
    atr_period: int = Field(default=14, ge=2)
    min_atr_pct: float = Field(
        default=0.0, ge=0, description="Volatilidade mínima (ATR/preço %) para operar"
    )
    max_atr_pct: float = Field(
        default=100.0, gt=0, description="Volatilidade máxima para operar"
    )

    # Filtros de qualidade de sinal
    min_confidence: float = Field(
        default=0.55, ge=0.0, le=1.0, description="Confiança mínima do sinal para executar"
    )
    require_trend_alignment: bool = Field(
        default=True, description="Exige alinhamento com a tendência da MA lenta"
    )

    @model_validator(mode="after")
    def _validate(self) -> "StrategyConfig":
        if self.ma_fast_period >= self.ma_slow_period:
            raise ValueError("ma_fast_period deve ser menor que ma_slow_period")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast deve ser menor que macd_slow")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("rsi_oversold deve ser menor que rsi_overbought")
        if self.min_atr_pct >= self.max_atr_pct:
            raise ValueError("min_atr_pct deve ser menor que max_atr_pct")
        return self


class SessionConfig(BaseSettings):
    """Janela de negociação e comportamento do agendador."""

    model_config = SettingsConfigDict(env_prefix="SESSION_", env_file=".env", extra="ignore")

    timezone: str = "America/Sao_Paulo"
    start_time: str = "09:00"
    end_time: str = "17:00"
    trade_on_weekends: bool = False
    weekday_whitelist: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 3, 4], description="0=segunda ... 6=domingo"
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError(f"Horário inválido: {v}. Use HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"Horário fora do intervalo: {v}")
        return v


class Settings(BaseSettings):
    """Configuração raiz da aplicação."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Seleção de corretora ---
    broker: Broker = Broker.PAPER
    account_mode: AccountMode = AccountMode.DEMO

    # --- Credenciais IQ Option ---
    iq_email: Optional[str] = None
    iq_password: Optional[str] = None

    # --- Credenciais Binance ---
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    binance_testnet: bool = True

    # --- Mercado ---
    symbol: str = "EURUSD"
    timeframe_minutes: int = Field(default=5, ge=1, le=1440)
    expiration_minutes: int = Field(default=5, ge=1, le=1440)
    auto_otc: bool = Field(
        default=True, description="Troca automaticamente para -OTC quando o mercado fecha"
    )
    candles_lookback: int = Field(default=300, ge=50, le=1000)

    # --- Operação ---
    dry_run: bool = Field(
        default=True, description="True = simula ordens sem enviar à corretora"
    )
    poll_interval_seconds: int = Field(default=5, ge=1, le=300)

    # --- API / Dashboard ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_token: Optional[str] = Field(
        default=None, description="Token para endpoints de escrita do painel"
    )

    # --- Persistência e logs ---
    database_url: str = f"sqlite:///{DATA_DIR / 'trading.db'}"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    # --- Subconfigurações ---
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)

    @model_validator(mode="after")
    def _validate_credentials(self) -> "Settings":
        """Falha rápido: conta real sem credencial é erro de configuração, não de runtime."""
        if self.broker is Broker.IQOPTION and not self.dry_run:
            if not (self.iq_email and self.iq_password):
                raise ValueError(
                    "IQ_EMAIL e IQ_PASSWORD são obrigatórios para operar na IQ Option. "
                    "Defina-os no arquivo .env"
                )
        if self.broker is Broker.BINANCE and not self.dry_run:
            if not (self.binance_api_key and self.binance_api_secret):
                raise ValueError(
                    "BINANCE_API_KEY e BINANCE_API_SECRET são obrigatórios. "
                    "Defina-os no arquivo .env"
                )
        return self

    @property
    def is_live(self) -> bool:
        """True apenas quando envia ordens reais em conta real."""
        return self.account_mode is AccountMode.REAL and not self.dry_run

    def masked(self) -> dict:
        """Versão segura para logs e API — nunca expõe segredos."""
        def mask(v: Optional[str]) -> Optional[str]:
            if not v:
                return None
            return f"{v[:3]}***{v[-2:]}" if len(v) > 6 else "***"

        return {
            "broker": self.broker.value,
            "account_mode": self.account_mode.value,
            "symbol": self.symbol,
            "timeframe_minutes": self.timeframe_minutes,
            "expiration_minutes": self.expiration_minutes,
            "dry_run": self.dry_run,
            "is_live": self.is_live,
            "iq_email": mask(self.iq_email),
            "binance_api_key": mask(self.binance_api_key),
            "strategy": self.strategy.name,
        }


# Moedas de cotação mais comuns na Binance. Um par spot é sempre
# BASE+QUOTE grudados, sem separador: BTCUSDT, ETHBTC, SOLBRL.
_QUOTES_BINANCE = (
    "USDT", "FDUSD", "USDC", "BUSD", "TUSD", "DAI",
    "BTC", "ETH", "BNB", "TRY", "EUR", "BRL", "GBP", "JPY", "ARS",
)

# Pares que só existem no mercado de câmbio (IQ Option), nunca na Binance.
_FOREX = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "EURCHF", "AUDJPY", "EURAUD", "USDBRL",
)


def checar_simbolo(broker: Broker, symbol: str) -> Optional[str]:
    """Detecta ativo incompatível com a corretora escolhida.

    Existe porque o erro natural é silencioso até a hora errada: com
    BROKER=binance e SYMBOL=EURUSD a configuração é formalmente válida,
    o robô conecta, e só falha ao pedir candles. Retorna a explicação
    (ou None quando o par é plausível).
    """
    s = (symbol or "").strip().upper()
    if not s:
        return None

    if broker is Broker.BINANCE:
        limpo = s.replace("/", "").replace("-", "").replace("_", "")
        if limpo in _FOREX:
            return (
                f"SYMBOL={symbol} é um par de câmbio (Forex), que a Binance "
                f"não negocia. Use um par de cripto, como BTCUSDT ou ETHUSDT."
            )
        if s != limpo:
            return (
                f"SYMBOL={symbol} tem separador. Na Binance o par é grudado: "
                f"{limpo}."
            )
        if not limpo.isalnum():
            return f"SYMBOL={symbol} tem caracteres inválidos para a Binance."
        if not limpo.endswith(_QUOTES_BINANCE):
            return (
                f"SYMBOL={symbol} não termina em uma moeda de cotação "
                f"conhecida (USDT, BTC, BRL...). Confira o par em "
                f"binance.com/pt-BR/markets."
            )

    elif broker is Broker.IQOPTION:
        if s.endswith(("USDT", "BUSD", "FDUSD")):
            return (
                f"SYMBOL={symbol} tem formato de par de cripto da Binance. "
                f"Na IQ Option o ativo é como EURUSD ou EURUSD-OTC."
            )

    return None


_settings: Optional[Settings] = None


def get_settings(reload: bool = False) -> Settings:
    """Singleton de configuração."""
    global _settings
    if _settings is None or reload:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _settings = Settings()
    return _settings
