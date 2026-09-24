# Comece aqui

Guia prático, na ordem. Não pule o passo 1.

---

## Sobre a senha: qual delas vale?

**A senha que vale é sempre a que está cadastrada no site da IQ Option.**

O arquivo `.env` e o GitHub não guardam "senhas válidas" — guardam apenas
uma cópia de texto do que você digitou. Quem tem essa cópia consegue entrar
na sua conta, porque é a mesma senha do site.

| Onde está | O que é | Risco |
|---|---|---|
| Site da IQ Option | A senha de verdade | — |
| Seu `.env` local | Cópia, para o robô fazer login | Baixo (só na sua máquina) |
| Histórico do GitHub | Cópia **antiga**, pública | **Alto** |

Se a senha antiga ainda funcionar no site, qualquer pessoa que leia o
histórico do GitHub entra na sua conta. Trocar a senha no site invalida a
cópia exposta — é isso que resolve.

O `.env` da sua máquina está seguro: ele é ignorado pelo Git (está no
`.gitignore`) e nunca foi enviado ao GitHub.

---

## Passo 1 — Troque sua senha da IQ Option (faça agora)

Sua senha da IQ Option está **em texto puro no histórico do GitHub**, em um
repositório público. Qualquer pessoa consegue lê-la, mesmo tendo eu já
removido o arquivo — o histórico do Git guarda todas as versões anteriores.

O que fazer, nesta ordem:

1. Entre em <https://iqoption.com> → perfil → **Segurança** → trocar senha.
   Use uma senha nova, que você não use em nenhum outro site.
2. Na mesma tela, ative a **verificação em duas etapas (2FA)**.
3. Se você usava essa mesma senha em outro lugar (e-mail, banco), troque lá
   também.

> Já fiz isto: [ ]

**Por que não basta apagar o arquivo:** o Git guarda o passado. Limpar de
verdade exige reescrever o histórico (`git filter-repo`) ou criar um
repositório novo. Trocar a senha resolve o risco imediato e é o que
importa hoje.

---

## Passo 2 — Entenda o que os testes mostraram

Você rodou o backtest várias vezes. O resumo, sem jargão:

**As 5 estratégias do robô, somadas, perderam 7,56% a cada operação.**
A "vantagem da casa" da IQ Option com payout de 85% é de 7,50%.

Os números batem. Isso significa que as estratégias não estavam prevendo
nada — estavam apenas pagando a taxa da corretora, operação após operação.

Para comparação:

| Jogo | Vantagem da casa |
|---|---|
| Roleta europeia | 2,70% |
| Roleta americana | 5,26% |
| **Opção binária, payout 85%** | **7,50%** |

Opção binária tem vantagem da casa **maior que a roleta**.

**E aquele resultado de 61,5% de acerto?** Foram 13 operações. Rodando o
mesmo comando 5 minutos depois, uma única operação a mais mudou o resultado
de -1,06 para +17,62. Com amostra desse tamanho, o acaso sozinho produz
qualquer coisa entre 26% e 82% de acerto.

---

## Passo 3 — Escolha o seu caminho

### Caminho A — Parar por aqui (o que eu recomendo)

Você já tem a resposta que o projeto foi feito para dar: **estas estratégias
não ganham dinheiro neste formato**. Seu prejuízo original, com 38,5% de
acerto, era matematicamente esperado.

Parar agora custa zero e você sai sabendo o porquê.

### Caminho B — Continuar testando, sem dinheiro real

Se quiser explorar mais, o próximo teste legítimo é ampliar a amostra.

**1.** Rode este comando (não precisa editar arquivo nenhum):

```powershell
python -m trading_bot.cli backtest --candles 3000 --holdout --timeframe 15
```

**2.** Confirme na primeira linha que o timeframe pegou:

```
Obtendo 3000 candles de EURUSD em 15 min (~31.2 dias de pregão)...
```

Se aparecer `em 5 min (~10.4 dias)`, a flag não foi aplicada — confira se
você digitou `--timeframe 15` no fim do comando.

**3.** Leia o veredito final:

| Resultado | O que significa | O que fazer |
|---|---|---|
| `REPROVADA FORA DA AMOSTRA` | Não funciona | Pare. Volte ao Caminho A |
| `INCONCLUSIVO` | Ainda faltam dados | Pare. Mais tentativas só aumentam a chance de erro |
| `NÃO COMPROVADA` | Pode ser sorte | Pare |
| `SOBREVIVEU` | Único resultado que vale | Vá para o Passo 4 |

**Regra importante:** rode **uma vez** e aceite o resultado. Cada nova
tentativa com parâmetros diferentes aumenta a chance de encontrar sorte e
confundi-la com vantagem — com 10 tentativas, essa chance chega a 40%.

### Caminho C — Operar em conta demo

Só se o Passo 3 der `SOBREVIVEU`. Nunca antes.

---

## Passo 4 — Se e somente se algo sobreviveu

**1.** No `.env`, confirme que está tudo assim:

```env
DRY_RUN=true
BROKER=iqoption
ACCOUNT_MODE=demo
RISK_PERCENT_STAKE=1.0
RISK_MAX_DAILY_LOSS_PCT=3.0
RISK_MAX_CONSECUTIVE_LOSSES=3
RISK_MAX_TRADES_PER_DAY=10
RISK_MARTINGALE_ENABLED=false
```

**2.** Rode o robô em simulação:

```powershell
python -m trading_bot.cli run
```

**3.** Deixe rodando por **2 a 4 semanas**. Compare o resultado real com o
que o backtest previu. Se divergirem, o backtest estava errado.

**Não passe para dinheiro real** sem essas semanas de comparação.

---

## Caminho Binance (spot) — por que a matemática muda

Nas binárias, cada operação já nasce com **7,5% contra você** (payout 85%).
No spot da Binance você compra e vende a preço real, pagando ~0,1% de taxa
por ordem — **0,2% ida e volta**. É cerca de **38 vezes menos custo**.

A diferença mais importante é outra: em binária o acerto precisa vencer o
payout, e 54,05% é só o empate. Em spot, o que decide é a relação entre o
ganho e a perda:

| razão alvo/stop | acerto necessário para empatar |
|---|---|
| 1x (alvo = stop) | 50,0% |
| 1,5x | 40,0% |
| 2x | 33,3% |
| 3x | 25,0% |

Com alvo 2x maior que o stop, **34% de acerto já dá lucro**. Isso é
impossível numa binária de payout 85%.

### Como rodar

```powershell
python -m trading_bot.cli backtest-spot --candles 3000 --timeframe 15 --stop 1.0 --target 2.0
```

O que cada opção faz:

| opção | significado |
|---|---|
| `--stop 1.0` | vende se cair 1% (limita a perda) |
| `--target 2.0` | vende se subir 2% (realiza o lucro) |
| `--fee 0.1` | taxa da Binance por ordem (padrão já correto) |
| `--slippage` | simula executar a preço pior que o pedido |
| `--max-bars` | fecha a posição após N candles, se nada foi tocado |

A coluna **payoff** no relatório é ganho médio ÷ perda média — em spot ela
importa mais que a coluna de acerto.

### Para backtestar você NÃO precisa de chave nenhuma

Os candles da Binance são dados públicos. Basta no `.env`:

```env
BROKER=binance
SYMBOL=BTCUSDT
TIMEFRAME_MINUTES=15
```

⚠️ **Troque o `SYMBOL`.** Se você vinha da IQ Option, ele está como
`EURUSD` — um par de câmbio, que a Binance não negocia. Na Binance o par
é de cripto e vem grudado, sem barra: `BTCUSDT`, `ETHUSDT`, `SOLBRL`.
O `validate` avisa quando corretora e ativo não combinam.

Deixe `BINANCE_API_KEY` e `BINANCE_API_SECRET` **vazios**. O robô conecta em
modo somente leitura, baixa o histórico e recusa qualquer envio de ordem.
Nem `python-binance` é necessário nessa etapa.

⚠️ Se você copiou `BINANCE_API_KEY=sua_chave` literalmente do exemplo, o
robô agora avisa em vez de tentar conectar com um valor falso. Apague o
conteúdo e deixe em branco.

### Backtest com dados reais da mainnet

```powershell
python -m trading_bot.cli backtest-spot --candles 3000 --stop 1.0 --target 2.0
```

Os candles vêm **sempre da mainnet**, mesmo com `BINANCE_TESTNET=true`. O
histórico da testnet é gerado por um motor de testes com liquidez
artificial — backtestar sobre ele mede ficção, não mercado.

### Só quando for operar de verdade

```powershell
python -m pip install python-binance
```

E no `.env`:

```env
BINANCE_API_KEY=sua_chave_real_aqui
BINANCE_API_SECRET=seu_segredo_real_aqui
BINANCE_TESTNET=true
DRY_RUN=true
```

**Comece pela testnet**: ambiente da própria Binance, com dinheiro
fictício. Crie as chaves em <https://testnet.binance.vision>.

Quando criar chaves reais, **nunca habilite saque** — marque apenas leitura
e negociação (Enable Reading + Enable Spot Trading).

---

## Comandos que você vai usar

```powershell
# Atualizar o projeto (sempre antes de testar)
git fetch origin
git reset --hard origin/arena/01a0c98e-rob-iqoption

# Ver se está tudo configurado
python -m trading_bot.cli validate

# Backtest honesto (o que importa)
python -m trading_bot.cli backtest --candles 3000 --holdout

# Mesma coisa, com amostra maior (candles de 15 min)
python -m trading_bot.cli backtest --candles 3000 --holdout --timeframe 15

# Painel de controle no navegador
python -m trading_bot.cli dashboard
# depois abra http://localhost:8000

# Backtest para Binance spot (mecânica diferente: stop e alvo)
python -m trading_bot.cli backtest-spot --candles 3000 --stop 1.0 --target 2.0

# Rodar o robô (respeita DRY_RUN do .env)
python -m trading_bot.cli run
```

---

## Sobre o martingale

O robô tem martingale, **desligado por padrão**. Deixe desligado.

A ideia é dobrar a aposta após cada perda. O problema: 7 derrotas seguidas
acontecem em 88,6% das sequências de 500 operações. Na 8ª você precisaria
apostar **128 vezes** a aposta inicial. É assim que contas zeram.

---

## A conta que explica tudo

Com payout de 85%, você precisa acertar **54,05%** apenas para empatar.

- Acertou 50%? Perde dinheiro.
- Acertou 53%? Ainda perde.
- Acertar 54,05% é empatar, sem lucro.

Acertar mais que isso, de forma consistente, significa prever a direção do
EURUSD nos próximos 5 minutos com mais frequência que o acaso — usando
indicadores que todo mundo no mercado já conhece e já estão no preço.

Os testes que você rodou mostraram que as 5 estratégias não conseguem.
