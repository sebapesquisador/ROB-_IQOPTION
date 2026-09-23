# 🚀 Guia Rápido - Bot Binance

## Passo 1: Instalar dependências

```bash
pip install -r requirements_binance.txt
```

## Passo 2: Obter chaves da API (Testnet)

1. Acesse: https://testnet.binance.vision/
2. Clique em **"Generate HMAC_SHA256 Key"**
3. Copie a **API Key** e **Secret Key**

## Passo 3: Configurar as chaves

**Opção A - Direto no código (mais simples):**

Edite `bot_binance.py` linha ~37:
```python
self.api_key = "cole_sua_api_key_aqui"
self.api_secret = "cole_sua_secret_key_aqui"
self.usar_testnet = True
```

**Opção B - Arquivo separado (mais seguro):**

1. Edite `config_api.py`:
   ```python
   TESTNET_API_KEY = "cole_sua_testnet_api_key_aqui"
   TESTNET_SECRET_KEY = "cole_sua_testnet_secret_key_aqui"
   ```

2. No `bot_binance.py`, adicione no topo:
   ```python
   from config_api import TESTNET_API_KEY, TESTNET_SECRET_KEY
   ```

3. E na linha ~37, substitua por:
   ```python
   self.api_key = TESTNET_API_KEY
   self.api_secret = TESTNET_SECRET_KEY
   ```

## Passo 4: Configurar o bot

Edite `bot_binance.py`:

```python
# Linha ~40 - Par de negociação
self.par_negociacao = "BTCUSDT"  # ou ETHUSDT, BNBUSDT, etc

# Linha ~41 - Timeframe
self.timeframe = "5m"  # 1m, 5m, 15m, 30m, 1h

# Linha ~42 - Valor por operação
self.valor_operacao_usdt = 15.0  # Mínimo ~10 USDT

# Linha ~39 - Estratégia
self.estrategia_escolhida = 3  # Escolha de 1 a 11
```

## Passo 5: Executar o bot

```bash
python bot_binance.py
```

## Passo 6: Monitorar

- Veja o terminal para logs em tempo real
- Abra `bot_binance.log` para histórico completo

---

## ⚙️ Estratégias Recomendadas para Iniciantes

### Estratégia 3 (Recomendada para testes)
```python
self.estrategia_escolhida = 3
self.rsi_periodo = 14
self.rsi_sobrevenda = 30.0
self.rsi_sobrecompra = 70.0
```

### Estratégia 11 (Bollinger Bands)
```python
self.estrategia_escolhida = 11
self.bb_periodo = 20
self.bb_desvio = 2.8
self.stop_loss_percent_est11 = 2.0
self.take_profit_percent_est11 = 1.0
```

---

## 🎯 Checklist Antes de Executar

- [ ] Dependências instaladas (`pip install -r requirements_binance.txt`)
- [ ] Chaves de API configuradas
- [ ] `usar_testnet = True` (para testes)
- [ ] Par de negociação configurado
- [ ] Valor de operação >= 10 USDT
- [ ] Estratégia escolhida (1-11)

---

## 🛠️ Problemas Comuns

### "Invalid API-key"
→ Verifique se copiou as chaves corretamente
→ Confirme se `usar_testnet = True`

### "MIN_NOTIONAL"
→ Aumente `valor_operacao_usdt` para pelo menos 15 USDT

### "Insufficient balance"
→ No Testnet: gere fundos em https://testnet.binance.vision/
→ No Mainnet: deposite fundos na sua conta

### Bot não faz trades
→ Normal! Ele espera as condições da estratégia
→ Veja os logs para entender o que está acontecendo
→ Teste com dados históricos primeiro

---

## 📊 Entendendo os Logs

```
💹 BTCUSDT: 43250.50000000 USDT  → Preço atual
🟢 Sinal COMPRA - RSI em sobrevenda (28.45)  → Condição detectada
✅ Ordem executada: 12345678  → Trade realizado
📊 ESTATÍSTICAS  → Resumo do desempenho
   Total de trades: 5
   Win Rate: 60.0%
   Lucro total: 12.50 USDT
```

---

## 🔄 Próximos Passos

1. **Teste no Testnet por pelo menos 1 semana**
2. **Analise os resultados e ajuste parâmetros**
3. **Experimente diferentes estratégias**
4. **Quando estiver confiante, use dinheiro real com MUITO cuidado**
5. **Comece com valores MUITO pequenos (10-20 USDT)**

---

## ⚠️ LEMBRE-SE

- Trading é arriscado
- Teste MUITO antes de usar dinheiro real
- Nunca invista mais do que pode perder
- Configure Stop Loss sempre
- Monitore o bot constantemente

Boa sorte! 🚀
