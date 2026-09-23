# 🤖 EA Price Action v2.0 - Bot IQ Option

Bot de trading automático adaptado do EA_PRICE_ACTION_v2.mq5 para funcionar na plataforma IQ Option.

## 📋 Características

### ✅ 11 Estratégias Implementadas

1. **Estratégia 1**: RSI Reversão (uma posição por vez)
2. **Estratégia 2**: RSI Acumulação com Inversão
3. **Estratégia 3**: RSI Acumulação com Saída RSI 50
4. **Estratégia 4**: Candle + MA21 + RSI Pullback
5. **Estratégia 5**: MA21 + MA5 + RSI
6. **Estratégia 6**: MA21 + MA5 + RSI Invertido (Contra-tendência)
7. **Estratégia 7**: Candle + MA21 Tendência
8. **Estratégia 8**: Candle + MA21 Invertido (HEDGE)
9. **Estratégia 9**: Candle + MA21 - Saída SL/TP
10. **Estratégia 10**: Candle + MA21 Invertido SL/TP (HEDGE)
11. **Estratégia 11**: Bollinger Bands - Múltiplas Posições

### 📊 Recursos

- ✅ Conta DEMO e REAL
- ✅ 10 estratégias completas de Price Action
- ✅ Metas diárias e totais
- ✅ Horário de negociação configurável
- ✅ Sistema de logs detalhado
- ✅ Indicadores técnicos: RSI, MA21, MA5
- ✅ Win Rate automático
- ✅ Estatísticas em tempo real

## 🚀 Instalação

### 1. Instale Python 3.8+

Baixe em: https://www.python.org/downloads/

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

## ⚙️ Configuração

Abra o arquivo `bot_iqoption.py` e configure:

### 1️⃣ Credenciais (OBRIGATÓRIO)

```python
self.email = "seu_email@exemplo.com"  # ← SEU EMAIL DA IQ OPTION
self.senha = "sua_senha_aqui"         # ← SUA SENHA DA IQ OPTION
```

### 2️⃣ Configurações de Trading

```python
self.estrategia_escolhida = 11      # Estratégia 1 a 11
self.ativo_base = "EURUSD"         # Par de moedas BASE (sem -OTC)
self.timeframe = 1                 # Tempo do candle (minutos)
self.valor_operacao = 1.0          # Valor por operação ($)
self.modo_pratica = True           # True = DEMO | False = REAL
self.usar_otc_automatico = True    # True = Detecta e usa OTC automaticamente
self.tempo_expiracao = 1           # Tempo de expiração (minutos)
```

**🌐 DETECÇÃO AUTOMÁTICA DE OTC:**
- O bot detecta automaticamente quando o mercado está fechado
- Muda para ativo OTC (exemplo: EURUSD → EURUSD-OTC)
- Funciona 24/7 sem intervenção manual

### 3️⃣ Metas

```python
self.meta_diaria = 5000.0
self.meta_total = 5000.0
```

### 4️⃣ Horário de Negociação

```python
self.usar_horario = True
self.hora_inicio = "09:00"
self.hora_fim = "18:30"
```

### 5️⃣ Parâmetros por Estratégia

#### Estratégias 1, 2, 3 (RSI):
```python
self.rsi_periodo = 10
self.rsi_sobrevenda = 25.0
self.rsi_sobrecompra = 75.0
self.rsi_saida_meio = 50.0
```

#### Estratégia 4 (Pullback MA21):
```python
self.ma21_periodo_est4 = 21
self.rsi_periodo_est4 = 14
self.stop_loss_est4 = 500.0
self.take_profit_est4 = 1000.0
```

#### Estratégias 5 e 6 (MA + RSI):
```python
self.ma21_periodo = 21
self.ma5_periodo = 5
self.rsi_periodo_est5 = 14
self.stop_loss_est5 = 500.0
self.take_profit_est5 = 1000.0
```

#### Estratégias 7 a 10 (Candle + MA21):
```python
self.ma21_periodo_est7 = 21
self.stop_loss_est7 = 500.0
self.take_profit_est7 = 1000.0
# (Similar para Est 8, 9 e 10)
```

## ▶️ Execução

```bash
python bot_iqoption.py
```

## 📊 Descrição das Estratégias

### 🔵 Estratégia 1 - RSI Reversão
- **Entrada**: RSI < 25 (COMPRA) ou RSI > 75 (VENDA)
- **Saída**: RSI retorna a 50
- **Tipo**: Uma posição por vez

### 🔵 Estratégia 2 - RSI Acumulação com Inversão
- **Entrada**: Acumula a cada cruzamento do RSI
- **Saída**: Inverte quando RSI cruza para o outro lado
- **Tipo**: Múltiplas posições

### 🔵 Estratégia 3 - RSI Acumulação RSI 50
- **Entrada**: Acumula a cada cruzamento
- **Saída**: RSI retorna a 50
- **Tipo**: Múltiplas posições

### 🔵 Estratégia 4 - Pullback MA21
- **Setup**: Candle a favor + RSI confirmando
- **Entrada**: Preço toca MA21 (pullback)
- **Saída**: SL/TP

### 🔵 Estratégia 5 - MA21 + MA5 + RSI
- **Entrada**: Close > MA21 > MA5 + RSI > 50 (COMPRA)
- **Entrada**: Close < MA21 < MA5 + RSI < 50 (VENDA)
- **Saída**: Retorno à MA5 ou TP

### 🔵 Estratégia 6 - MA + RSI Invertido (Hedge)
- **Entrada**: CONTRA a tendência detectada
- **Saída**: Retorno à MA5 ou TP
- **Tipo**: Contra-tendência

### 🔵 Estratégia 7 - Candle + MA21
- **Entrada**: Candle + filtro MA21
- **Saída**: Inversão automática
- **Tipo**: Tendência

### 🔵 Estratégia 8 - Candle + MA21 Invertido
- **Entrada**: Contra a tendência (HEDGE da Est 7)
- **Saída**: Inversão automática
- **Tipo**: Contra-tendência

### 🔵 Estratégia 9 - Candle + MA21 SL/TP
- **Entrada**: Igual Estratégia 7
- **Saída**: APENAS SL/TP (sem inversão)
- **Tipo**: Tendência

### 🔵 Estratégia 10 - Candle + MA21 Invertido SL/TP
- **Entrada**: Contra tendência (HEDGE da Est 9)
- **Saída**: APENAS SL/TP (sem inversão)
- **Tipo**: Contra-tendência

### 🔵 Estratégia 11 - Bollinger Bands (Múltiplas Posições)
- **Entrada CALL**: Preço atual < Banda Inferior
- **Entrada PUT**: Preço atual > Banda Superior
- **Saída**: Quando preço retorna à Média Móvel (banda do meio) OU TP/SL
- **Tipo**: Reversão à média com múltiplas posições simultâneas
- **Parâmetros Ajustáveis**:
  - `bb_periodo = 20` - Período das Bandas de Bollinger
  - `bb_desvio = 2.0` - Número de desvios padrão
  - `stop_loss_est11 = 200.0` - Stop Loss em pontos
  - `take_profit_est11 = 100.0` - Take Profit em pontos
- **Observações**: 
  - Permite abertura de múltiplas posições simultaneamente
  - Ideal para mercados com alta volatilidade e reversões à média
  - Ajuste os parâmetros BB conforme o ativo e timeframe utilizados

## 📁 Estrutura de Arquivos

```
IQOption_PriceAction_Bot/
├── bot_iqoption.py       # Código principal do bot
├── requirements.txt      # Dependências Python
├── README.md            # Este arquivo
└── bot_iqoption.log     # Log de operações (gerado automaticamente)
```

## ⚠️ Avisos Importantes

1. **Teste SEMPRE em conta DEMO primeiro!**
2. **Use capital que você pode perder**
3. **Trading envolve riscos significativos**
4. **Resultados passados não garantem resultados futuros**
5. **Ajuste os parâmetros conforme seu perfil de risco**

## 🔧 Solução de Problemas

### Erro de conexão
- Verifique suas credenciais
- Confirme que sua conta IQ Option está ativa
- Tente desabilitar VPN/Proxy

### Bot não abre posições
- Verifique o horário de negociação
- Confirme que o ativo está disponível
- Verifique o saldo da conta

### Indicadores não calculam
- Aumente o histórico de candles
- Verifique se o timeframe está correto

## 📝 Logs

O bot gera logs em:
- **Arquivo**: `bot_iqoption.log`
- **Console**: Saída em tempo real

Exemplo de log:
```
2025-11-03 10:30:45 - INFO - 📊 EST 1: Sinal COMPRA | RSI: 22.45
2025-11-03 10:30:46 - INFO - ✅ Posição CALL aberta | ID: 123456
2025-11-03 10:31:00 - INFO - ✅ TRADE VENCEDOR | Lucro: $18.50
2025-11-03 10:31:00 - INFO - 📊 Win Rate: 75.0% (3/4)
```

## 🤝 Suporte

Em caso de dúvidas:
1. Revise este README
2. Verifique os logs do bot
3. Confirme suas configurações

## 📜 Licença

Este bot é uma adaptação do EA_PRICE_ACTION_v2.mq5 para uso pessoal.

---

**🚀 Bons trades!**
