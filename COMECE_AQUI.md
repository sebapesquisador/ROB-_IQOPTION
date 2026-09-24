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

| razão alvo/stop | empate (sem taxa) | **empate real (taxa 0,1%)** |
|---|---|---|
| 1x (alvo = stop) | 50,0% | 54,5% |
| 1,5x | 40,0% | 43,5% |
| 2x | 33,3% | **40,0%** |
| 3x | 25,0% | 28,6% |

⚠️ **Olhe sempre a última coluna.** A taxa aparece dos dois lados da conta:
encolhe o ganho e engorda a perda. Com alvo 2% e stop 1%, a razão nominal
de 2,00x vira **1,50x** líquida, e o empate sobe de 33,3% para **40,0%**.
Uma estratégia com 38% de acerto parece vencedora na coluna do meio e
perde dinheiro na vida real. O relatório mostra os dois números, com
destaque para o que vale.

Ainda assim, 40% é muito melhor que os 54,05% da binária — e a diferença
cresce quanto maior o alvo em relação ao stop.

Quanto menor o alvo, mais a taxa pesa: um scalp de 0,3% com stop de 0,3%
precisa de **62,5%** de acerto. Alvos apertados são devorados pelo custo.

### A linha "aleatório" é a mais importante do relatório

O relatório inclui uma referência que entra em candles **sorteados**, sem
olhar para o preço. Ela existe para responder à única pergunta que importa:
*33% de acerto é ruim, ou é isso que qualquer entrada produz?*

Com stop 1% e alvo 2%, o preço tende a tocar o stop duas vezes mais que o
alvo. O acerto esperado de um sorteio é:

$$\frac{stop}{stop + alvo} = \frac{1}{1+2} = 33{,}3\%$$

Verificado no código, num passeio aleatório de 60 mil candles: 31,9%
obtido contra 33,3% teóricos.

Ou seja: **33% de acerto não significa nada.** É o piso da mecânica. Uma
estratégia só está fazendo algum trabalho se ficar acima dessa linha — e
só é lucrativa se passar do equilíbrio líquido (40,0% no exemplo).

O relatório mostra também a faixa entre a melhor e a pior semente. Se a
sua estratégia cai dentro dela, ela é indistinguível de sorteio.

Para desligar: `--no-baseline`.

### "E se o problema forem só os parâmetros?"

É a objeção certa, e tem resposta medível:

```powershell
python -m trading_bot.cli backtest-spot --symbol BTCUSDT --candles 30000 --sweep
```

A varredura testa 9 combinações de stop e alvo — de 0,5%/0,5% a 2%/6% — e
em cada uma compara a melhor estratégia contra o melhor de 5 sorteios.

Duas cautelas embutidas:

- **Os sinais são calculados uma vez e reaproveitados.** As entradas são
  as mesmas em todas as linhas, então a única coisa variando é a barreira.
- **Melhor contra melhor.** Comparar a melhor de 5 estratégias com a
  *média* do acaso fabricaria vantagem do nada — foi assim que a fase da
  IQ Option produziu uma ilusão de +9pp. Nos testes internos, essa
  correção sozinha derrubou a vantagem aparente de +2,8pp para +1,0pp.

Se nenhuma linha vencer, a conclusão é que o stop e o alvo decidem
**quantas** operações ganham, não **se** há o que ganhar. Isso depende da
entrada prever algo.

Leva alguns minutos com 30 mil candles.

### Caminho 3: dados que não são o preço (funding rate)

As cinco estratégias liam só a cotação e todas empataram com sorteio. Era
previsível: RSI, MACD e Bollinger são funções públicas do mesmo histórico
que todo mundo vê. Se previssem o próximo movimento, a previsão já estaria
no preço.

O **funding rate** é diferente em espécie. Não é calculado do preço — é um
pagamento real entre participantes, a cada 8 horas, que mantém o contrato
perpétuo colado no spot. Quando positivo, quem está comprado paga a quem
está vendido. É uma medida de **posicionamento**, não de histórico.

```powershell
python -m trading_bot.cli funding --symbol BTCUSDT --periodos 1000
```

Dado público, sem chave. 1000 pagamentos ≈ 333 dias.

O relatório tem duas metades, e a diferença entre elas é o ponto:

| metade | o que é | pode falhar? |
|---|---|---|
| **carrego** | taxa observada; vender perpétuo e comprar spot fica neutro em preço e recebe funding | não — é aritmética |
| **sinal** | funding alto prevê queda? | sim — precisa passar no teste |

O teste do sinal separa os eventos em quintis de funding, mede o retorno
seguinte de cada grupo e usa **teste de permutação**: embaralha qual
retorno pertence a qual funding milhares de vezes para ver com que
frequência o acaso produz a diferença observada. Com `--holdout-split`, a
fatia final nunca participa de escolha nenhuma.

Calibração verificada em dados sintéticos: 1 falso positivo em 20 amostras
sem efeito (esperado a 5%), e detecção consistente de efeitos plantados.

Opções úteis: `--horizonte 24` (mede retorno de 24h em vez de 8h),
`--grupos 3`, `--permutacoes 10000`.

### Duas armadilhas que o relatório agora evita

**1. "Ganhar do sorteio" não é lucro.** A varredura mostra a coluna
`falta` — distância até o equilíbrio líquido. Uma estratégia pode ter
sinal real e ainda assim perder dinheiro, se o sinal for menor que a taxa.
O que paga conta é `falta` positiva, não `diferença` positiva.

**2. Comparar o melhor de muitos infla tudo.** Rodei a varredura sobre um
passeio aleatório, onde não existe sinal por construção. Resultado: a
coluna `diferença` deu **+1,6pp de média e até +4,6pp**, e a coluna
`falta` chegou a **+8,8pp** — tudo ruído. O p-valor com correção de
Bonferroni reprovou **as 12 linhas**, como devia.

Por isso a regra: só acredite na linha se ela tiver `falta` positiva
**e** `p` abaixo do alpha mostrado no cabeçalho.

### Comprar e segurar: o benchmark que humilha robôs

O relatório mostra quanto o ativo variou no período. É a comparação mais
desconfortável e a mais honesta: num mercado que subiu 60%, uma estratégia
só comprada pode fechar no lucro e mesmo assim ter sido muito pior que não
fazer nada.

Vale no sentido inverso também — se o ativo caiu, perder pouco é
resultado.

### Salvando a saída num arquivo

Funciona normalmente:

```powershell
python -m trading_bot.cli backtest-spot --symbol BTCUSDT --candles 30000 --sweep | Tee-Object RETORNO.txt
```

Ao redirecionar, o Windows usa a codificação antiga (cp1252) em vez de
UTF-8. Símbolos como `→` e `✔` não existem lá e antes derrubavam o
programa. Agora eles viram `->` e `OK` automaticamente — os acentos do
português, que a cp1252 tem, continuam certos.

### O tamanho da amostra é o que mais engana

3000 candles de 15 min cobrem só ~31 dias e costumam render 10 a 40
operações — sem força estatística nenhuma. Diferente da IQ Option, a
Binance entrega **anos** de histórico de graça. Peça bastante:

```powershell
python -m trading_bot.cli backtest-spot --symbol BTCUSDT --candles 30000 --stop 1.0 --target 2.0
```

30000 candles de 15 min ≈ 10 meses. A busca é paginada de 1000 em 1000 e
leva alguns segundos. O relatório calcula sozinho quantos candles faltam
para você chegar a 30 operações.

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

## Estratégia Williams %R (`wpr_extremes`)

O Williams %R mede **onde o fechamento caiu dentro da faixa dos últimos N
candles**. Vai de -100 (fechou na mínima da janela) a 0 (fechou na máxima).
Perto de -100, quem vendia se esgotou; perto de 0, quem comprava.

Diferente das outras cinco, esta estratégia **decide também a saída**. As
outras só escolhem a entrada e deixam o stop ou o alvo fecharem a posição.

### Os cinco números, no `.env`

```
STRAT_NAME=wpr_extremes
STRAT_WPR_PERIOD=20       # tamanho da janela, em candles
STRAT_WPR_BUY=-95         # entra COMPRADO abaixo disso
STRAT_WPR_SELL=-5         # entra VENDIDO acima disso
STRAT_WPR_EXIT_BUY=-20    # encerra a COMPRA acima disso
STRAT_WPR_EXIT_SELL=-80   # encerra a VENDA abaixo disso
```

```
 -100 ─────────────────────────────────────────────────── 0
   │                                                      │
   └── COMPRA (-95)          sai da compra (-20) ──┐      │
       sai da venda (-80) ──────────────┘          └── VENDA (-5)
```

O robô **recusa iniciar** se os níveis não fizerem sentido (saída antes da
entrada, zonas de compra e venda cruzadas) e diz qual variável corrigir.
Níveis mais frouxos (-80 / -30) geram muito mais operações; mais apertados
(-98 / -10), poucas e raras.

### Testando

```bash
# Só a perna comprada (é o que a Binance spot permite de verdade)
python -m trading_bot.cli backtest-spot --strategy wpr_extremes \
  --symbol BTCUSDT --candles 30000 --timeframe 15 \
  --stop 1.0 --target 3.0 --fee 0.1

# Incluindo a perna vendida (exige margem na vida real)
python -m trading_bot.cli backtest-spot --strategy wpr_extremes \
  --symbol BTCUSDT --candles 30000 --timeframe 15 --allow-short
```

### Duas limitações que você precisa saber

1. **`--allow-short` não simula o custo de aluguel.** Vender a descoberto
   custa juros que este motor ignora. Serve para estudar o sinal, não para
   prever o lucro.

2. **Ao vivo, a saída do WPR não é executada.** A interface de corretora
   deste projeto abre ordem com vencimento e espera o resultado — nenhuma
   corretora aqui sabe encerrar posição antes da hora. Rodando ao vivo, as
   *entradas* seguem a estratégia e as *saídas* não: é uma estratégia
   diferente da que você testou. O robô grava um aviso no log e acende uma
   bandeira no painel ao iniciar, justamente para isso não passar batido.
   Enquanto essa peça não existir, trate o `wpr_extremes` como estratégia
   **de backtest**.


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
