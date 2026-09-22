# 🤖 EA Price Action v2.0 - Bot Binance

Bot de trading automático adaptado para funcionar na Binance com as mesmas 11 estratégias de Price Action.

## 🆕 Diferenças da versão IQ Option

### ✅ Adaptações para Binance

1. **API Binance**: Usa `python-binance` ao invés da API da IQ Option
2. **Testnet disponível**: Suporte para conta demo da Binance (Testnet)
3. **Stop Loss / Take Profit**: Implementado com porcentagens ao invés de pips
4. **Pares de negociação**: Suporte para qualquer par (BTCUSDT, ETHUSDT, BNBUSDT, etc)
5. **Timeframes flexíveis**: 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d
6. **Trading Spot**: Opera no mercado à vista (para SHORT seria necessário Futures)

## 🚀 Instalação

### 1. Instale Python 3.8+

Baixe em: https://www.python.org/downloads/

### 2. Instale as dependências

```bash
pip install -r requirements_binance.txt
```

## 🔑 Configuração das Chaves de API

### Opção 1: Testnet (Recomendado para testes)

1. Acesse: https://testnet.binance.vision/
2. Clique em "Generate HMAC_SHA256 Key"
3. Copie a **API Key** e **Secret Key**
4. Edite o arquivo `bot_binance.py`:
   ```python
   self.api_key = "SUA_API_KEY_AQUI"
   self.api_secret = "SEU_SECRET_AQUI"
   self.usar_testnet = True  # Deixe como True
   ```

### Opção 2: Conta Real (USE COM CUIDADO!)

1. Acesse: https://www.binance.com/pt-BR/my/settings/api-management
2. Crie uma nova API Key
3. **IMPORTANTE**: Ative apenas as permissões de "Spot Trading" e "Reading"
4. **NUNCA** ative "Enable Withdrawals"
5. Configure restrição por IP para maior segurança
6. Edite o arquivo `bot_binance.py`:
   ```python
   self.api_key = "SUA_API_KEY_AQUI"
   self.api_secret = "SUA_SECRET_KEY_AQUI"
   self.usar_testnet = False  # Altere para False
   ```

## ⚙️ Configuração do Bot

Abra o arquivo `bot_binance.py` e configure:

### 1️⃣ Credenciais (OBRIGATÓRIO)

```python
self.api_key = "SUA_API_KEY_AQUI"
self.api_secret = "SUA_SECRET_KEY_AQUI"
self.usar_testnet = True  # True = Testnet | False = Real
```

### 2️⃣ Par de Negociação

```python
self.par_negociacao = "BTCUSDT"  # BTC, ETH, BNB, etc
self.timeframe = "5m"  # 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d
```

### 3️⃣ Valor por Operação

```python
self.valor_operacao_usdt = 15.0  # Mínimo geralmente 10 USDT
```

### 4️⃣ Escolha da Estratégia

```python
self.estrategia_escolhida = 3  # 1 a 11
```

### 5️⃣ Parâmetros da Estratégia

Para estratégias com RSI:
```python
self.rsi_periodo = 14
self.rsi_sobrevenda = 30.0
self.rsi_sobrecompra = 70.0
```

Para estratégias com Stop Loss/Take Profit:
```python
self.stop_loss_percent_est4 = 2.0  # 2%
self.take_profit_percent_est4 = 1.0  # 1%
```

### 6️⃣ Metas

```python
self.meta_diaria = 100.0  # Meta em USDT
self.meta_total = 500.0   # Meta em USDT
```

### 7️⃣ Horário de Negociação

```python
self.usar_horario = True
self.hora_inicio = "00:00"
self.hora_fim = "23:59"
```

## 📊 Estratégias Disponíveis

### Estratégia 1 - RSI Reversão
- Compra quando RSI < 30
- Vende quando RSI > 70
- Mantém apenas 1 posição por vez

### Estratégia 2 - RSI Acumulação
- Acumula compras em sobrevenda
- Fecha todas ao detectar sobrecompra

### Estratégia 3 - RSI com Saída em 50
- Compra em sobrevenda
- Sai quando RSI volta a 50

### Estratégia 4 - Candle + MA21 + RSI
- Usa média móvel de 21 períodos
- Compra quando preço > MA21 e RSI favorável
- Com Stop Loss e Take Profit

### Estratégia 5 - MA21 + MA5 + RSI
- Cruzamento de médias móveis
- Confirmação com RSI
- Com Stop Loss e Take Profit

### Estratégia 11 - Bollinger Bands
- Compra na banda inferior
- Vende na banda superior
- Múltiplas posições permitidas

## ▶️ Como Executar

```bash
python bot_binance.py
```

## 📝 Logs

O bot gera um arquivo `bot_binance.log` com todas as operações realizadas.

## ⚠️ Avisos Importantes

### Sobre o Trading Spot vs Futures

⚠️ **IMPORTANTE**: Este bot opera no mercado **SPOT** da Binance:
- ✅ Pode comprar (LONG)
- ❌ NÃO pode vender a descoberto (SHORT) - apenas fecha posições

Para operar SHORT real, seria necessário:
- Usar Binance Futures
- Implementar margem e alavancagem
- Gerenciar liquidação

### Sobre Segurança

🔐 **NUNCA compartilhe suas chaves de API!**
- Use sempre restrição por IP
- Não ative permissão de saque
- Teste primeiro no Testnet
- Comece com valores baixos

### Sobre Riscos

⚡ **Trading envolve risco de perda total do capital**
- Use apenas capital que pode perder
- Teste extensivamente antes de operar real
- Configure Stop Loss adequados
- Monitore o bot regularmente

## 📈 Dicas de Uso

### Para Testes

1. Use o Testnet primeiro
2. Teste cada estratégia separadamente
3. Ajuste os parâmetros gradualmente
4. Monitore os logs constantemente

### Para Produção

1. Comece com valores MUITO pequenos
2. Use apenas 1-2% do capital por operação
3. Defina metas realistas
4. Configure alertas
5. Revise o desempenho diariamente

## 🛠️ Troubleshooting

### Erro "Invalid API-key"
- Verifique se copiou as chaves corretamente
- Confirme se está usando Testnet ou Mainnet correto

### Erro "MIN_NOTIONAL"
- Aumente o `valor_operacao_usdt` (mínimo ~10 USDT)

### Erro "Insufficient balance"
- Verifique seu saldo na Binance
- No Testnet, você precisa "gerar" fundos no site

### Bot não executa trades
- Verifique se está dentro do horário configurado
- Confirme se as condições da estratégia estão sendo atendidas
- Veja os logs em `bot_binance.log`

## 📚 Recursos Adicionais

- [Documentação Binance API](https://binance-docs.github.io/apidocs/spot/en/)
- [Python-Binance Docs](https://python-binance.readthedocs.io/)
- [Binance Testnet](https://testnet.binance.vision/)

## 📞 Suporte

- Leia os logs para entender erros
- Verifique a documentação da Binance
- Teste no Testnet antes de usar dinheiro real

---

**⚠️ AVISO LEGAL**: Este bot é fornecido apenas para fins educacionais. O autor não se responsabiliza por perdas financeiras. Trading de criptomoedas envolve alto risco.
