# Trading Bot v2.0 — IQ Option & Binance

Robô de trading automatizado com gestão de risco, backtesting e painel de
controle web.

> ⚠️ **Leia [`AUDITORIA.md`](AUDITORIA.md) antes de usar.** Ele documenta os
> problemas encontrados na versão anterior — incluindo credenciais expostas que
> exigem ação imediata da sua parte — e explica por que a matemática do payout
> torna este tipo de operação tão difícil.

---

## O que mudou

| | Antes | Agora |
|---|---|---|
| Credenciais | Hardcoded no código, commitadas | `.env`, fora do Git, mascaradas nos logs |
| Gestão de risco | Nenhuma | 8 travas antes de cada ordem |
| Backtesting | Inexistente | Completo, com veredito automático |
| Testes | 0 | 146 |
| Painel | Somente leitura | Controle total do robô |
| Arquitetura | 1 classe de 1.322 linhas | Módulos separados e testáveis |
| Persistência | JSON reescrito inteiro | SQLite com WAL |

---

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # edite com suas configurações
```

Dependências das corretoras (instale só a que for usar):

```bash
# IQ Option
pip install -U git+https://github.com/iqoptionapi/iqoptionapi.git

# Binance
pip install python-binance
```

---

## Uso

```bash
# 1. Valide a configuração (não conecta em nada)
python -m trading_bot.cli validate

# 2. Veja as estratégias disponíveis
python -m trading_bot.cli strategies

# 3. Teste as estratégias em dados históricos
python -m trading_bot.cli backtest --candles 3000 --payout 0.85

# 4. Suba o painel de controle
python -m trading_bot.cli dashboard
#    → http://localhost:8000

# 5. Ou rode direto no terminal
python -m trading_bot.cli run --dry-run
```

---

## Configuração

Tudo vive no `.env`. Os campos que mais importam:

```env
BROKER=paper              # paper | iqoption | binance
DRY_RUN=true              # true = simula ordens (comece SEMPRE assim)
SYMBOL=EURUSD
TIMEFRAME_MINUTES=5
EXPIRATION_MINUTES=5

STRAT_NAME=confluence
STRAT_MIN_CONFIDENCE=0.60

RISK_PERCENT_STAKE=1.0            # % do saldo por operação
RISK_MAX_DAILY_LOSS_PCT=5.0       # para tudo ao perder 5% no dia
RISK_MAX_CONSECUTIVE_LOSSES=3
RISK_MARTINGALE_ENABLED=false     # mantenha false
```

`BROKER=paper` usa um simulador interno — permite testar toda a stack sem
credencial e sem risco.

---

## Estratégias

| Nome | Tipo | Ideia |
|---|---|---|
| `rsi_reversal` | Reversão | RSI saindo de zona extrema, filtrado por ADX baixo |
| `trend_pullback` | Tendência | Recuo à média rápida com ADX confirmando força |
| `bollinger_reversion` | Reversão | Rejeição de banda com retorno para dentro |
| `macd_momentum` | Momentum | Cruzamento do MACD alinhado à tendência |
| `confluence` | Híbrida | Votação ponderada de 5 sinais, exige 65% de acordo |

Cada uma devolve um sinal com **confiança de 0 a 1**. Sinais abaixo de
`STRAT_MIN_CONFIDENCE` são descartados.

### Criando a sua

```python
from trading_bot.core.strategies import Strategy, register
from trading_bot.core.models import Direction, Signal

@register("minha_estrategia")
class MinhaEstrategia(Strategy):
    """Descrição que aparece no CLI e no painel."""

    def generate(self, df):
        cur = self.last_closed(df)      # SEMPRE o candle fechado, nunca iloc[-1]
        if cur["rsi"] < 30:
            return Signal(Direction.CALL, 0.7, self.name, "RSI em sobrevenda",
                          {"rsi": float(cur["rsi"])})
        return Signal.none(self.name, "sem setup")
```

O teste `test_no_lookahead` roda automaticamente contra toda estratégia
registrada e falha se ela olhar o candle em formação.

---

## Gestão de risco

Nenhuma ordem é enviada sem passar por `RiskManager.approve()`, que verifica:

1. Cooldown por sequência de derrotas
2. Stop de perda diária
3. Drawdown máximo sobre o pico de capital
4. Meta diária atingida (parar no lucro também é estratégia)
5. Teto de operações por dia
6. Posições simultâneas
7. Intervalo mínimo entre entradas
8. Dimensionamento válido face ao saldo

Ao estourar os limites 2, 3 ou 4, o robô entra em estado `HALTED` e só volta a
operar com intervenção manual.

---

## A matemática que você precisa conhecer

Com payout de 85%, você ganha $0,85 ao acertar e perde $1,00 ao errar:

```
acerto mínimo para empatar = 1 / (1 + 0,85) = 54,05%
```

100 operações de $10 com 50% de acerto:

```
50 × (+$8,50) + 50 × (−$10,00) = −$75,00
```

**Acertar metade das vezes não empata — perde.** Por isso o backtester exibe o
ponto de equilíbrio e reprova qualquer estratégia sem vantagem real acima dele.

---

## Painel

```bash
python -m trading_bot.cli dashboard
```

- Iniciar / pausar / parar o robô
- KPIs: saldo, resultado do dia, taxa de acerto vs. equilíbrio, fator de lucro,
  drawdown, próxima entrada
- Barra de consumo do limite de perda diária
- Último sinal com confiança e indicadores que o motivaram
- Gráficos de capital e de preço com indicadores
- Backtest sob demanda, comparando todas as estratégias
- Histórico de operações e log de eventos em tempo real (SSE)

Para expor na rede, defina `API_TOKEN` no `.env` — os endpoints de escrita
passam a exigir o header `X-API-Token`.

---

## Testes

```bash
pytest                              # 146 testes
pytest --cov=trading_bot            # com cobertura
```

---

## Estrutura

```
trading_bot/
├── core/          config, models, indicators, risk, engine, storage
│   └── strategies/
├── brokers/       base, paper, iqoption, binance
├── backtest/      engine de backtesting
├── api/           FastAPI + painel
└── cli.py
tests/             146 testes
legacy/            código da versão anterior, para referência
```

---

## Segurança

- Credenciais apenas em `.env` (no `.gitignore`)
- Logs filtram senhas, tokens e chaves automaticamente
- Endpoints de leitura nunca retornam segredos (há teste garantindo isso)
- Confirmação explícita no CLI antes de operar com dinheiro real
- `DRY_RUN=true` é o padrão

**Nunca** commite o `.env`. **Nunca** habilite permissão de saque nas chaves de
API da Binance.

---

## Aviso

Trading automatizado de opções binárias é atividade de altíssimo risco. A
estrutura de payout garante vantagem matemática à corretora. Este software é
uma ferramenta de engenharia — não é conselho financeiro e não promete lucro.
Opere apenas com capital que você pode perder integralmente.
