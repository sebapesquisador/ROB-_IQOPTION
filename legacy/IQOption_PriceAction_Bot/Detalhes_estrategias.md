# 📊 Detalhes das 11 Estratégias - EA Price Action v2.0

Este documento descreve em detalhes as condições de entrada e saída de cada uma das 11 estratégias implementadas no bot.

---

## 🔵 Estratégia 1 - RSI Reversão (Posição Única)

### 📈 Entrada CALL (Compra)
- **Condição**: RSI < 30 (zona de sobrevenda)
- **Lógica**: Mercado oversold, expectativa de reversão para cima

### 📉 Entrada PUT (Venda)
- **Condição**: RSI > 70 (zona de sobrecompra)
- **Lógica**: Mercado overbought, expectativa de reversão para baixo

### 🚪 Saída
- **Inversão automática**: Quando sinal oposto aparece
- **Exemplo**: Se está em CALL e RSI > 70, fecha CALL e abre PUT
- **Característica**: Mantém sempre UMA posição aberta (não acumula)

### ⚙️ Parâmetros
- `rsi_periodo = 14` - Período do RSI
- `rsi_sobrecompra = 70` - Limite superior
- `rsi_sobrevenda = 30` - Limite inferior

---

## 🔵 Estratégia 2 - RSI Acumulação com Inversão

### 📈 Entrada CALL (Compra)
- **Condição**: RSI < 30
- **Lógica**: Acumula posições de compra em sobrevenda

### 📉 Entrada PUT (Venda)
- **Condição**: RSI > 70
- **Lógica**: Acumula posições de venda em sobrecompra

### 🚪 Saída
- **Inversão e acumulação**: Fecha TODAS as posições atuais e abre nova no sentido oposto
- **Exemplo**: Se tem 3 CALLs e RSI > 70, fecha os 3 CALLs e abre 1 PUT
- **Característica**: Permite múltiplas posições no mesmo sentido

### ⚙️ Parâmetros
- `rsi_periodo = 14`
- `rsi_sobrecompra = 70`
- `rsi_sobrevenda = 30`

---

## 🔵 Estratégia 3 - RSI Acumulação com Saída RSI 50

### 📈 Entrada CALL (Compra)
- **Condição**: RSI < 30
- **Lógica**: Acumula compras em sobrevenda

### 📉 Entrada PUT (Venda)
- **Condição**: RSI > 70
- **Lógica**: Acumula vendas em sobrecompra

### 🚪 Saída
- **CALL**: Fecha quando RSI > 50 (retornou ao equilíbrio)
- **PUT**: Fecha quando RSI < 50 (retornou ao equilíbrio)
- **Lógica**: Aguarda normalização do mercado para realizar lucro
- **Característica**: Permite múltiplas posições, saída individual quando RSI volta ao meio

### ⚙️ Parâmetros
- `rsi_periodo = 14`
- `rsi_sobrecompra = 70`
- `rsi_sobrevenda = 30`
- Saída fixa em RSI 50

---

## 🔵 Estratégia 4 - Candle + MA21 + RSI Pullback

### 📈 Entrada CALL (Compra)
- **Condições simultâneas**:
  1. Candle fecha **ACIMA** da MA21 (tendência de alta)
  2. RSI < 50 (pullback, correção temporária)
- **Lógica**: Compra na correção de uma tendência de alta confirmada

### 📉 Entrada PUT (Venda)
- **Condições simultâneas**:
  1. Candle fecha **ABAIXO** da MA21 (tendência de baixa)
  2. RSI > 50 (pullback, correção temporária)
- **Lógica**: Vende na correção de uma tendência de baixa confirmada

### 🚪 Saída
- **Inversão automática**: Quando condições opostas são satisfeitas
- **Característica**: Uma posição por vez, segue tendência com filtro RSI

### ⚙️ Parâmetros
- `ma_periodo = 21` - Período da Média Móvel
- `rsi_periodo = 14`
- RSI 50 como filtro de pullback

---

## 🔵 Estratégia 5 - MA21 + MA5 + RSI

### 📈 Entrada CALL (Compra)
- **Condições simultâneas**:
  1. Preço > MA21 (tendência principal de alta)
  2. MA5 > MA21 (tendência de curto prazo confirma)
  3. RSI < 50 (entrada em pullback)
- **Lógica**: Tripla confirmação de tendência de alta com entrada em correção

### 📉 Entrada PUT (Venda)
- **Condições simultâneas**:
  1. Preço < MA21 (tendência principal de baixa)
  2. MA5 < MA21 (tendência de curto prazo confirma)
  3. RSI > 50 (entrada em pullback)
- **Lógica**: Tripla confirmação de tendência de baixa com entrada em correção

### 🚪 Saída
- **Inversão automática**: Quando condições opostas aparecem
- **Característica**: Estratégia conservadora com 3 filtros

### ⚙️ Parâmetros
- `ma_periodo = 21`
- `ma_curta_periodo = 5`
- `rsi_periodo = 14`

---

## 🔵 Estratégia 6 - MA21 + MA5 + RSI Invertido (Contra-tendência)

### 📈 Entrada CALL (Compra)
- **Condições simultâneas**:
  1. Preço < MA21 (tendência de baixa)
  2. MA5 < MA21 (confirma baixa)
  3. RSI > 50 (mostra força compradora contra a tendência)
- **Lógica**: HEDGE - Compra contra a tendência de baixa

### 📉 Entrada PUT (Venda)
- **Condições simultâneas**:
  1. Preço > MA21 (tendência de alta)
  2. MA5 > MA21 (confirma alta)
  3. RSI < 50 (mostra força vendedora contra a tendência)
- **Lógica**: HEDGE - Vende contra a tendência de alta

### 🚪 Saída
- **Inversão automática**: Quando condições opostas são satisfeitas
- **Característica**: Estratégia contra-tendência (maior risco, maior recompensa)

### ⚙️ Parâmetros
- `ma_periodo = 21`
- `ma_curta_periodo = 5`
- `rsi_periodo = 14`

---

## 🔵 Estratégia 7 - Candle + MA21 Tendência

### 📈 Entrada CALL (Compra)
- **Condições**:
  1. Candle atual fecha **ACIMA** da MA21
  2. Candle anterior fechou **ABAIXO** da MA21
- **Lógica**: Entrada no momento exato do cruzamento para cima

### 📉 Entrada PUT (Venda)
- **Condições**:
  1. Candle atual fecha **ABAIXO** da MA21
  2. Candle anterior fechou **ACIMA** da MA21
- **Lógica**: Entrada no momento exato do cruzamento para baixo

### 🚪 Saída
- **Inversão automática**: Quando cruzamento oposto ocorre
- **Característica**: Estratégia de cruzamento puro, simples e eficaz

### ⚙️ Parâmetros
- `ma_periodo = 21`

---

## 🔵 Estratégia 8 - Candle + MA21 Invertido (HEDGE)

### 📈 Entrada CALL (Compra)
- **Condições**:
  1. Candle atual fecha **ABAIXO** da MA21
  2. Candle anterior fechou **ACIMA** da MA21
- **Lógica**: HEDGE - Compra quando cruza para baixo (contra-tendência)

### 📉 Entrada PUT (Venda)
- **Condições**:
  1. Candle atual fecha **ACIMA** da MA21
  2. Candle anterior fechou **ABAIXO** da MA21
- **Lógica**: HEDGE - Vende quando cruza para cima (contra-tendência)

### 🚪 Saída
- **Inversão automática**: Quando cruzamento oposto ocorre
- **Característica**: Inverso da Estratégia 7, opera contra o cruzamento

### ⚙️ Parâmetros
- `ma_periodo = 21`

---

## 🔵 Estratégia 9 - Candle + MA21 com SL/TP

### 📈 Entrada CALL (Compra)
- **Condições**:
  1. Candle atual fecha **ACIMA** da MA21
  2. Candle anterior fechou **ABAIXO** da MA21
- **Lógica**: Mesmo que Estratégia 7, mas com gerenciamento SL/TP

### 📉 Entrada PUT (Venda)
- **Condições**:
  1. Candle atual fecha **ABAIXO** da MA21
  2. Candle anterior fechou **ACIMA** da MA21
- **Lógica**: Mesmo que Estratégia 7, mas com gerenciamento SL/TP

### 🚪 Saída
- **APENAS por Stop Loss ou Take Profit**
- **NÃO inverte** automaticamente
- **Stop Loss**: `stop_loss_est9 = 200.0` pontos
- **Take Profit**: `take_profit_est9 = 100.0` pontos
- **Característica**: Aguarda SL/TP, não fecha por sinal oposto

### ⚙️ Parâmetros
- `ma_periodo = 21`
- `stop_loss_est9 = 200.0`
- `take_profit_est9 = 100.0`

---

## 🔵 Estratégia 10 - Candle + MA21 Invertido com SL/TP (HEDGE)

### 📈 Entrada CALL (Compra)
- **Condições**:
  1. Candle atual fecha **ABAIXO** da MA21
  2. Candle anterior fechou **ACIMA** da MA21
- **Lógica**: HEDGE da Estratégia 9 com SL/TP

### 📉 Entrada PUT (Venda)
- **Condições**:
  1. Candle atual fecha **ACIMA** da MA21
  2. Candle anterior fechou **ABAIXO** da MA21
- **Lógica**: HEDGE da Estratégia 9 com SL/TP

### 🚪 Saída
- **APENAS por Stop Loss ou Take Profit**
- **NÃO inverte** automaticamente
- **Stop Loss**: `stop_loss_est10 = 200.0` pontos
- **Take Profit**: `take_profit_est10 = 100.0` pontos
- **Característica**: Contra-tendência com proteção SL/TP

### ⚙️ Parâmetros
- `ma_periodo = 21`
- `stop_loss_est10 = 200.0`
- `take_profit_est10 = 100.0`

---

## 🔵 Estratégia 11 - Bollinger Bands (Múltiplas Posições)

### 📈 Entrada CALL (Compra)
- **Condição**: Preço atual < Banda Inferior
- **Cálculo Banda Inferior**: Média Móvel - (Desvio Padrão × `bb_desvio`)
- **Lógica**: Preço muito baixo (oversold), expectativa de reversão para a média

### 📉 Entrada PUT (Venda)
- **Condição**: Preço atual > Banda Superior
- **Cálculo Banda Superior**: Média Móvel + (Desvio Padrão × `bb_desvio`)
- **Lógica**: Preço muito alto (overbought), expectativa de reversão para a média

### 🚪 Saída
- **Saída principal**: Quando preço retorna à **Banda do Meio** (Média Móvel)
- **Saída alternativa**: Stop Loss ou Take Profit
- **Stop Loss**: `stop_loss_est11 = 200.0` pontos
- **Take Profit**: `take_profit_est11 = 100.0` pontos
- **Característica**: 
  - Permite **múltiplas posições simultâneas**
  - Ideal para mercados voláteis com reversão à média
  - Cada toque na banda pode gerar nova posição

### 📊 Cálculo das Bandas
```
Banda do Meio (MM) = Média Móvel Simples (período)
Desvio Padrão = Desvio padrão dos preços (período)
Banda Superior = MM + (Desvio Padrão × bb_desvio)
Banda Inferior = MM - (Desvio Padrão × bb_desvio)
```

### ⚙️ Parâmetros Ajustáveis
- `bb_periodo = 20` - Período da Média Móvel e Desvio Padrão
- `bb_desvio = 2.0` - Número de desvios padrão
  - **Valores menores** (1.5): Bandas mais estreitas, mais sinais, menos confiáveis
  - **Valores maiores** (2.5-3.0): Bandas mais largas, menos sinais, mais confiáveis
- `stop_loss_est11 = 200.0` - Proteção contra movimento contrário
- `take_profit_est11 = 100.0` - Realização de lucro parcial

### 💡 Dicas de Uso
- **Mercados laterais**: BB funciona muito bem (reversão à média)
- **Mercados em tendência**: Cuidado, pode gerar muitos sinais falsos
- **Volatilidade alta**: Aumente `bb_desvio` para 2.5 ou 3.0
- **Volatilidade baixa**: Diminua `bb_desvio` para 1.5
- **Timeframes maiores**: Sinais mais confiáveis (M5, M15)
- **Timeframes menores**: Mais sinais, maior frequência (M1)

---

## 📋 Resumo Comparativo

| Estratégia | Tipo | Posições Simultâneas | Saída |
|-----------|------|---------------------|--------|
| 1 - RSI Reversão | Reversão | Única | Inversão |
| 2 - RSI Acumulação Inv | Reversão | Múltiplas | Inversão |
| 3 - RSI Acumulação 50 | Reversão | Múltiplas | RSI 50 |
| 4 - Candle+MA21+RSI | Tendência | Única | Inversão |
| 5 - MA21+MA5+RSI | Tendência | Única | Inversão |
| 6 - MA21+MA5+RSI Inv | Contra-tendência | Única | Inversão |
| 7 - Candle+MA21 | Tendência | Única | Inversão |
| 8 - Candle+MA21 Inv | Contra-tendência | Única | Inversão |
| 9 - Candle+MA21 SL/TP | Tendência | Única | SL/TP |
| 10 - Candle+MA21 Inv SL/TP | Contra-tendência | Única | SL/TP |
| 11 - Bollinger Bands | Reversão à média | Múltiplas | Média/SL/TP |

---

## 🎯 Recomendações de Uso

### Mercados em Tendência Forte
- ✅ Estratégia 7 (Candle + MA21)
- ✅ Estratégia 9 (Candle + MA21 SL/TP)
- ✅ Estratégia 5 (MA21 + MA5 + RSI)

### Mercados Laterais (Range)
- ✅ Estratégia 1, 2, 3 (RSI)
- ✅ Estratégia 11 (Bollinger Bands)

### Proteção com HEDGE
- ✅ Estratégia 6 (contra Estratégia 5)
- ✅ Estratégia 8 (contra Estratégia 7)
- ✅ Estratégia 10 (contra Estratégia 9)

### Acumulação de Posições
- ✅ Estratégia 2 (RSI Acumulação)
- ✅ Estratégia 3 (RSI Acumulação 50)
- ✅ Estratégia 11 (Bollinger Bands)

---

## ⚠️ Observações Importantes

1. **Sempre teste em DEMO** antes de usar em conta real
2. **Ajuste os parâmetros** conforme o ativo e timeframe
3. **Estratégias HEDGE** (6, 8, 10) têm maior risco
4. **Múltiplas posições** (2, 3, 11) requerem capital adequado
5. **SL/TP** (9, 10, 11) protegem contra movimentos adversos
6. **Combine estratégias** para diversificação (ex: 7 + 11)

---

**📅 Última atualização**: 03 de novembro de 2025  
**🤖 Bot**: EA Price Action v2.0 para IQ Option  
**📊 Total de Estratégias**: 11
