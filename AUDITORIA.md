# Auditoria Técnica — ROB-_IQOPTION

Análise do código original e registro do que foi refeito.

---

## 1. Resumo executivo

O projeto original tinha uma base de ideias válida, mas a implementação
apresentava **três falhas que tornavam o robô perigoso na prática**:

1. **Credenciais reais commitadas em repositório público** (senha da IQ Option
   e chaves da Binance em texto puro).
2. **Ausência total de gestão de risco** — nenhum stop diário, nenhum limite de
   drawdown, nenhum controle de sequência de perdas.
3. **Nenhuma forma de validar se as estratégias davam lucro** antes de expor
   dinheiro real.

O log do próprio robô (`bot_iqoption.log`) confirma o resultado:
**38,5% de acerto em 26 operações, prejuízo de $35,25.**

---

## 2. O que estava bom

Nem tudo precisava ser jogado fora. Estes pontos foram preservados:

| Ponto | Comentário |
|---|---|
| Separação por corretora | Ter `bot_iqoption.py` e `bot_binance.py` separados foi uma boa intuição — virou a camada `brokers/` com interface comum. |
| Variedade de estratégias | As ideias (RSI, MA21, pullback, Bollinger) são válidas e continuam presentes, reescritas. |
| Painel web | Ter um painel já era um diferencial. Foi expandido de somente-leitura para controle real. |
| Documentação em português | Boa iniciativa. Os guias de erro (`ERRO_TIMESTAMP.md`, `ERRO_ATIVO_SUSPENSO.md`) mostram diagnóstico real de problemas. |
| Fallback Binary → Digital | A intenção de tentar outro mercado quando um falha é correta — mas a execução tinha um bug grave (ver 3.6). |

---

## 3. Problemas encontrados

### 3.1 🔴 CRÍTICO — Credenciais expostas no Git

```python
# bot_iqoption.py, linhas 39-40
self.email = "<email real exposto>"
self.senha = "<senha real exposta>"

# bot_binance.py, linhas 41-42
self.api_key = "<chave real exposta>"
self.api_secret = "<secret real exposto>"
```

Não havia `.gitignore`. Qualquer pessoa com acesso ao repositório tinha acesso
direto à conta.

**Ação necessária de sua parte (o código não resolve isso sozinho):**
1. Trocar a senha da IQ Option **agora**.
2. Revogar as chaves da Binance em *API Management*.
3. Ativar 2FA nas duas contas.
4. As chaves continuam no histórico do Git mesmo após a correção — só some com
   reescrita de histórico (`git filter-repo`) ou recriando o repositório.

**Corrigido:** credenciais agora vêm de `.env` (fora do Git), com `.gitignore`
completo, validação na inicialização e filtro que mascara segredos nos logs.

---

### 3.2 🔴 CRÍTICO — Nenhuma gestão de risco

O robô antigo só parava em duas situações: meta de lucro atingida ou crash.

```python
self.meta_diaria = 5000.0   # com stake de $5, exigiria centenas de vitórias
self.meta_total = 5000.0
```

Não existia:
- stop de perda diária
- limite de drawdown
- controle de derrotas consecutivas
- dimensionamento proporcional ao saldo (stake fixo de $5 independentemente de
  ter $50 ou $5.000 em conta)
- intervalo mínimo entre operações

**Corrigido:** módulo `core/risk.py` com 8 verificações independentes antes de
cada ordem. Nenhuma ordem é enviada sem passar por `RiskManager.approve()`.
Coberto por 27 testes.

---

### 3.3 🔴 CRÍTICO — A matemática do payout era ignorada

Esta é a falha conceitual mais importante, e nenhum documento do projeto a
mencionava.

Em opções binárias com payout de 85%, você ganha $0,85 ao acertar e perde
$1,00 ao errar. O ponto de equilíbrio é:

```
taxa de acerto mínima = 1 / (1 + payout)
payout 85%  →  54,05% de acerto apenas para EMPATAR
payout 80%  →  55,56%
```

Com 50% de acerto (o que uma moeda honesta daria), 100 operações de $10 rendem:

```
50 × (+$8,50)  +  50 × (−$10,00)  =  −$75,00
```

**Uma estratégia que acerta metade das vezes perde dinheiro de forma garantida.**
O robô antigo, com 38,5%, estava muito abaixo disso.

**Corrigido:** o backtester calcula e exibe o ponto de equilíbrio, e emite
veredito automático reprovando estratégias sem vantagem real.

---

### 3.4 🟠 ALTO — Look-ahead bias (repintura de sinais)

As estratégias liam `df.iloc[-1]` — o candle **ainda em formação**:

```python
rsi_atual = df['rsi'].iloc[-1]        # muda a cada segundo
if rsi_atual < self.rsi_sobrevenda:
    self.abrir_posicao("CALL")
```

Combinado com o loop de 1 segundo, isso significa que o sinal aparecia e
desaparecia conforme o preço oscilava dentro do candle. O robô entrava numa
condição que frequentemente deixava de existir no fechamento.

**Corrigido:** todas as estratégias usam `df.iloc[-2]` (último candle fechado),
e o engine avalia **uma vez por candle**. Há um teste automatizado
(`test_no_lookahead`) que roda contra todas as estratégias e falha se alguma
mudar de sinal quando o candle em formação é alterado.

---

### 3.5 🟠 ALTO — O robô ficava cego durante cada operação

```python
def verificar_resultado_operacao(self, order_id):
    tempo_espera = 0
    while tempo_espera < 300:        # bloqueia até 5 MINUTOS
        resultado = self.api.check_win_v3(order_id)
        time.sleep(1)
        tempo_espera += 1
```

Chamada de dentro do loop principal, essa função **congelava o robô inteiro**.
Em timeframe de 5 minutos, o robô perdia o candle seguinte inteiro.

**Corrigido:** `check_order()` é não bloqueante; ordens abertas são reconciliadas
a cada ciclo. Teste `test_reconcile_is_non_blocking` garante retorno em <2s.

---

### 3.6 🟠 ALTO — Fallback de expiração corrompia as operações

```python
for exp_time in [1, 2, 5]:
    resultado = self.api.buy_digital_spot(self.ativo, valor, action, exp_time)
    if check: break
```

Se a estratégia foi calibrada para 5 minutos mas a ordem entrava com 1 minuto,
o resultado não tem relação alguma com o sinal gerado. O robô operava com um
horizonte temporal diferente do que analisou.

**Corrigido:** a expiração é fixa e respeitada. Se o ativo não está disponível,
a ordem é recusada e registrada — em vez de executada de forma errada.

---

### 3.7 🟠 ALTO — Detecção de OTC por regra chutada

```python
if hora < 13 or hora >= 20:
    return f"{self.ativo_base}-OTC"
```

Essa regra força OTC durante o pregão de Londres (08:00–13:00 UTC), quando o
mercado normal está aberto e líquido. O comentário no código admitia a incerteza
("tecnicamente impossível, mas por segurança").

**Corrigido:** `resolve_symbol()` consulta a disponibilidade real via
`get_all_open_time()`, com cache de 5 minutos.

---

### 3.8 🟡 MÉDIO — RSI calculado de forma não padrão

```python
ganho = (delta.where(delta > 0, 0)).rolling(window=periodo).mean()
perda = (-delta.where(delta < 0, 0)).rolling(window=periodo).mean()
rs = ganho / perda          # divisão por zero quando não há perdas
```

Dois problemas: média simples em vez da suavização de Wilder (o RSI do robô
não batia com o RSI da plataforma), e divisão por zero gerando `NaN` silencioso.

**Corrigido:** `indicators.rsi()` usa `ewm(alpha=1/period)` (Wilder) e trata o
caso de perda zero. Validado contra casos extremos nos testes.

---

### 3.9 🟡 MÉDIO — Estratégias "invertidas" eram redundantes

Das 11 estratégias, as de número 6, 8 e 10 eram apenas o inverso das de número
5, 7 e 9. Isso parte da premissa de que "se a estratégia perde, o inverso ganha"
— **o que é falso em opções binárias**: por causa do payout abaixo de 100%,
tanto A quanto não-A podem perder dinheiro.

As estratégias 7/9 e 8/10 eram idênticas na prática: diferiam apenas em
parâmetros de stop loss em pips que **nunca eram usados no código** (em opção
binária a saída é sempre a expiração).

**Corrigido:** consolidadas em 5 estratégias reais e distintas, cada uma com
lógica própria e confiança calibrada.

---

### 3.10 🟡 MÉDIO — Estado em JSON sem atomicidade

`state.json` e `history.json` eram reescritos inteiros a cada atualização, sem
transação. Um crash durante a escrita corrompia o arquivo. O histórico era
limitado a 100 registros, impossibilitando análise de longo prazo.

**Corrigido:** SQLite com WAL — atômico, concorrente e consultável. Permite
análise por estratégia, por dia e reconstrução da curva de capital.

---

### 3.11 🟡 MÉDIO — Painel era somente leitura

O `dashboard/app.py` recebia números por POST e exibia. Não era possível
iniciar, parar, pausar, trocar estratégia ou entender por que uma entrada não
aconteceu.

**Corrigido:** painel com controle real (iniciar/pausar/parar), edição de
configuração, backtest sob demanda, streaming por SSE e visibilidade do motivo
de cada bloqueio de risco.

---

### 3.12 🟢 BAIXO — Outros pontos

| Problema | Correção |
|---|---|
| Deus-classe de 1.322 linhas misturando tudo | Separada em config / models / indicators / strategies / risk / brokers / engine / storage |
| `except Exception` engolindo erros | Exceções tipadas (`BrokerError`, `OrderRejected`) e log estruturado |
| Zero testes automatizados | 146 testes cobrindo indicadores, risco, estratégias, backtest, engine e API |
| Log crescendo sem limite | Rotação de 10MB × 5 arquivos |
| `lucro_diario` nunca resetava à meia-noite | `DayBook` com virada automática de dia |
| Dependências sem versão fixa | `requirements.txt` com versões mínimas |
| Nenhuma validação de configuração | Pydantic valida tudo na inicialização, com `validate` no CLI |

---

## 4. O que foi construído

```
trading_bot/
├── core/
│   ├── config.py          Configuração tipada e validada (.env)
│   ├── models.py          Candle, Signal, Order, PerformanceStats
│   ├── indicators.py      RSI, MA, Bollinger, MACD, ATR, ADX, Estocástico
│   ├── risk.py            RiskManager — 8 travas de proteção
│   ├── engine.py          Orquestrador com máquina de estados
│   ├── storage.py         Persistência SQLite
│   ├── logging_setup.py   Logs com rotação e mascaramento de segredos
│   └── strategies/        5 estratégias plugáveis
├── brokers/
│   ├── base.py            Interface comum
│   ├── paper.py           Simulador para testes
│   ├── iqoption.py        IQ Option
│   └── binance.py         Binance Spot
├── backtest/engine.py     Backtester com veredito automático
├── api/server.py          FastAPI + painel de controle
└── cli.py                 run | dashboard | backtest | validate | strategies
```

**146 testes automatizados, todos passando.**

---

## 5. Resultado do backtest das novas estratégias

Rodado sobre 3.000 candles com payout de 85%:

```
estratégia             trades   acerto  vantagem      lucro     PF    DD%
bollinger_reversion       297    52.9%     -1.2p     -75.26   0.94   17.6
macd_momentum             170    49.4%     -4.6p    -142.20   0.83   20.6
rsi_reversal               56    37.5%    -16.6p    -159.73   0.49   18.8
trend_pullback            447    49.2%     -4.8p    -342.56   0.81   39.8
confluence               1209    48.4%     -5.7p    -733.00   0.81   79.3
```

**Todas reprovadas.** E isso é o sistema funcionando corretamente.

Este teste rodou sobre dados sintéticos (passeio aleatório), onde por definição
não existe padrão previsível. O resultado — todas as estratégias convergindo
para ~50% de acerto e perdendo o equivalente ao spread do payout — é exatamente
a resposta matematicamente correta.

**A lição:** indicadores técnicos clássicos, sozinhos, não produzem vantagem
suficiente para superar um payout de 85%. Era o que acontecia com o robô antigo,
só que sem instrumentação para perceber.

Rode o backtest com **dados reais** da sua conta antes de qualquer decisão:

```bash
python -m trading_bot.cli backtest --candles 5000 --payout 0.85
```

---

### 5.1 Por que "acerto alto" não basta: significância estatística

Um backtest real de 43 dias do EURUSD (3000 candles de 5 min) produziu:

| estratégia | trades | acerto | vantagem | p-valor | veredito |
|---|---|---|---|---|---|
| rsi_reversal | 45 | 66,7% | +12,6pp | 0,060 | NÃO COMPROVADA |

À primeira vista parece excelente: 66,7% de acerto contra um equilíbrio de
54,05%. Mas são apenas 45 operações. O teste binomial mostra que o acaso
produz esse resultado — ou melhor — em **1 de cada 17 amostras**, mesmo numa
estratégia sem vantagem nenhuma.

Pior: comparamos **5 estratégias** e ficamos com a melhor. A chance de ao
menos uma parecer boa por pura sorte é de **26%**. É o problema das
comparações múltiplas — quanto mais se testa, mais fácil encontrar sorte e
confundi-la com habilidade.

Por isso o veredito passou a exigir p-valor abaixo de **0,01** (0,05
corrigido por Bonferroni para as 5 estratégias), além dos critérios
anteriores de amostra mínima, vantagem e drawdown. Para confirmar uma
vantagem real de +12,6pp com confiança seriam necessárias **~93 operações**
— cerca de 89 dias no ritmo observado.

Agir sobre os 45 trades seria apostar dinheiro real em ruído.

### 5.2 OTC não é o mesmo ativo

Fora do horário de pregão o robô cai automaticamente para o par `-OTC`.
É útil para não travar, mas **invalida a comparação**: o preço OTC é gerado
pela própria corretora, não vem do mercado interbancário. São séries de
preço diferentes, com volatilidade e microestrutura próprias.

Duas rodadas consecutivas do mesmo `rsi_reversal` ilustram o ponto:

| instrumento | período | trades | acerto | p-valor |
|---|---|---|---|---|
| EURUSD | 43,2 dias | 45 | 66,7% | 0,060 |
| EURUSD-OTC | 31,2 dias | 34 | 64,7% | 0,141 |

Números parecidos, mas **não são evidência acumulada** — são dois ativos
distintos. Não se pode somar as amostras nem tratar a segunda como
confirmação da primeira. O CLI passou a avisar quando o backtest rodou em
OTC, e `--no-otc` força a avaliação apenas do par real.

### 5.3 É possível ganhar dinheiro em opções binárias?

A resposta honesta tem duas partes.

**Matematicamente não é impossível — mas a barreira é brutal.**

Com payout de 85%, cada operação a 50% de acerto tem valor esperado de
**-7,50%**. Isso é a vantagem da casa, e ela se compara assim:

| Jogo | Vantagem da casa |
|---|---|
| Blackjack (estratégia básica) | 0,50% |
| Roleta europeia | 2,70% |
| Roleta americana | 5,26% |
| **Binária payout 85%** | **7,50%** |
| **Binária payout 80%** | **10,00%** |

Opção binária tem vantagem da casa **maior que a roleta**. Apostando 2% do
capital por operação a 50% de acerto, o capital decai de $1.000 para $222
em 1.000 operações — sem nenhum azar, apenas pela matemática.

Para empatar é preciso acertar **54,05%**: prever a direção do EURUSD em 5
minutos com 8% mais frequência que uma moeda, de forma persistente.

**Com vantagem real, o lucro existe** — 56% de acerto rende +3,60% por
operação. O problema é comprovar que a vantagem é real:

| Acerto real | Trades para comprovar | Tempo a 1 trade/dia |
|---|---|---|
| 56% | ~5.130 | 14,1 anos |
| 58% | ~1.244 | 3,4 anos |
| 60% | ~546 | 1,5 anos |

Vantagens pequenas são indistinguíveis de sorte em qualquer amostra que se
consiga coletar numa vida útil de estratégia. E mesmo com 56% comprovado,
apostar 10% do capital leva à ruína em **35% das simulações**.

**O teste do filtro de confiança**

Elevar `--min-confidence` faz `bollinger_reversion` passar de -75,26 para
+33,90 (60,7% de acerto). Parece a solução — não é. O número de operações
despenca de 297 para 28, e o p-valor fica em 0,304: sem significância
alguma. Com 0,85 sobra **1 operação**. Isso não é encontrar vantagem, é
reduzir a amostra até o ruído parecer sinal. É overfitting puro.

**Conclusão:** os backtests não provam que ganhar é impossível. Provam que
nenhuma das 5 estratégias técnicas testadas supera o payout neste ativo, e
que o payout de 85% é uma barreira mais alta que a da roleta. Quem ganha de
forma consistente em binárias opera com vantagem estrutural (informação,
latência, arbitragem de preço), não com indicadores sobre candles — que é
o que este robô, e qualquer robô de análise técnica, faz.

### 5.4 Duas rodadas com 5 minutos de diferença

O mesmo comando, no mesmo ativo, executado às 16:13 e às 16:18 — a segunda
com meia hora a mais de candles:

| rodada | trades | acerto | lucro | veredito |
|---|---|---|---|---|
| 16:13 | 13 | 53,9% | **-1,06** | INCONCLUSIVO |
| 16:18 | 13 | 61,5% | **+17,62** | INCONCLUSIVO |

A diferença entre "perde dinheiro" e "lucra 17 dólares" foi **uma única
operação**: 7 vitórias em 13 viraram 8 em 13. Um trade representa 7,7% de
uma amostra desse tamanho, e desloca o acerto em 7,7 pontos percentuais.

Enquanto isso, o agregado das 5 estratégias — 570 operações — mal se moveu:

| rodada | operações | resultado por operação |
|---|---|---|
| 16:13 | 569 | -8,10% |
| 16:18 | 570 | -7,56% |
| *teórico (vantagem da casa)* | — | *-7,50%* |

É a lei dos grandes números visível em duas linhas. O desvio padrão do
acerto cai com a raiz do tamanho da amostra:

| operações | desvio padrão | faixa típica do acaso |
|---|---|---|
| 13 | 13,82pp | 26,4% a 81,7% |
| 50 | 7,05pp | 40,0% a 68,1% |
| 200 | 3,52pp | 47,0% a 61,1% |
| 570 | 2,09pp | 49,9% a 58,2% |
| 2000 | 1,11pp | 51,8% a 56,3% |

Com 13 operações, qualquer acerto entre 26% e 82% é compatível com uma
estratégia sem vantagem alguma. Por isso o veredito INCONCLUSIVO não é
timidez do sistema: é a única leitura defensável. E por isso um backtest
que exibe "61,5% de acerto" sem informar o tamanho da amostra é pior que
inútil — é enganoso.

## 6. Recomendações

### Antes de usar dinheiro real

1. **Troque as credenciais expostas** (item 3.1) — prioridade máxima.
2. Rode backtest com dados reais do seu ativo e horário.
3. Se nenhuma estratégia mostrar vantagem positiva **consistente**, não opere.
   Ajustar parâmetros até o backtest ficar bonito é *overfitting* — funciona no
   passado e falha no futuro.
4. Se alguma passar, rode em `DRY_RUN=true` por 2 a 4 semanas e compare o
   resultado real com o do backtest.
5. Só então considere conta real, começando com `RISK_PERCENT_STAKE=0.5`.

### Configuração de risco sugerida para início

```env
RISK_PERCENT_STAKE=0.5
RISK_MAX_DAILY_LOSS_PCT=3.0
RISK_MAX_CONSECUTIVE_LOSSES=3
RISK_MAX_TRADES_PER_DAY=10
RISK_MARTINGALE_ENABLED=false
```

### Sobre o martingale

Está implementado, mas **desligado por padrão e recomendo manter assim**. Com
payout de 85%, dobrar após perdas exige acertar rápido só para recuperar; sete
derrotas seguidas (evento comum em 200 operações) exigiriam uma aposta 128×
maior que a inicial. É o caminho mais rápido para zerar uma conta.

---

## 7. Aviso

Trading automatizado de opções binárias é atividade de altíssimo risco. A
estrutura de payout garante vantagem matemática à corretora. Este software é
uma ferramenta de engenharia — não é conselho financeiro e não promete lucro.
Opere apenas com capital que você pode perder integralmente.
