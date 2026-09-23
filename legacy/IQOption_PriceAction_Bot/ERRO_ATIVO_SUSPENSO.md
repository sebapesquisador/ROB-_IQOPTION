# ⚠️ Solução: Ativo Suspenso (Cannot purchase an option)

## 🔍 O que significa este erro?

Quando você vê:
```
⚠️ Binary Option retornou | Check: False | ID: Cannot purcchase an option (active is suspended)
```

Significa que o **ativo está temporariamente suspenso** na IQ Option.

---

## 📋 Por que acontece?

### 1️⃣ **Mercado FOREX Fechado**
O mercado FOREX (pares como EURUSD, GBPUSD, etc.) fecha:
- **Fim de semana**: Sexta 21:00 GMT → Domingo 21:00 GMT
- **Feriados**: Alguns feriados internacionais
- **Baixa liquidez**: Madrugada e horários específicos

### 2️⃣ **Horários de Baixa Volatilidade**
- Madrugada (00h-06h horário de Brasília)
- Almoço em NY (12h-14h)
- Transição entre sessões (asiática/europeia/americana)

### 3️⃣ **Suspensão Temporária da IQ Option**
- Problemas técnicos
- Manutenção do ativo
- Decisão da corretora

---

## ✅ Soluções Implementadas

### **Detecção Automática de OTC** 🤖

O bot agora:

1. **Detecta quando o ativo está suspenso**
2. **Automaticamente tenta com OTC** (exemplo: EURUSD → EURUSD-OTC)
3. **Registra no log** o que está acontecendo

### **Log Esperado (versão corrigida):**

```
📈 Abrindo posição CALL
   Ativo: EURUSD | Valor: $5.0 | Exp: 1min
⚠️ Binary Option retornou | Check: False | ID: Cannot purcchase an option (active is suspended)
🔄 Ativo suspenso! Tentando com EURUSD-OTC...
✅ Binary Option OTC executada | ID: 12345678
✅ Posição CALL aberta | ID: 12345678
```

---

## 🛠️ Como Configurar

### **Ativar OTC Automático** (já está ativado por padrão)

No arquivo `bot_iqoption.py`, linha ~47:

```python
self.usar_otc_automatico = True  # ← Garanta que está True
```

### **Verificar Ativo Base**

No arquivo `bot_iqoption.py`, linha ~43:

```python
self.ativo_base = "EURUSD"  # ← Sem -OTC no final!
```

**IMPORTANTE:** 
- Use apenas o nome base (EURUSD, GBPUSD, BTCUSD)
- **NÃO** coloque "-OTC" aqui
- O bot adiciona "-OTC" automaticamente quando necessário

---

## 🕐 Quando o Mercado OTC Funciona

### **Mercados OTC estão disponíveis 24/7**
- ✅ Fim de semana
- ✅ Feriados
- ✅ Madrugada
- ✅ Qualquer horário

### **Diferenças OTC vs Normal:**
| Característica | Mercado Normal | Mercado OTC |
|---------------|----------------|-------------|
| Horário | Segunda-Sexta (horário comercial) | 24h/7 dias |
| Liquidez | Alta | Moderada a Baixa |
| Spread | Menor | Maior |
| Disponibilidade | Limitada | Sempre disponível |

---

## 🎯 Checklist de Troubleshooting

- [ ] `usar_otc_automatico = True` ✅
- [ ] `ativo_base` sem "-OTC" no final ✅
- [ ] Verificar logs: bot tentou OTC automaticamente?
- [ ] Horário atual (fim de semana ou madrugada?)
- [ ] Saldo suficiente na conta?

---

## 📊 Ativos Recomendados para OTC

### **Sempre Disponíveis em OTC:**
- ✅ EURUSD-OTC
- ✅ GBPUSD-OTC
- ✅ USDJPY-OTC
- ✅ AUDUSD-OTC
- ✅ USDCAD-OTC

### **Criptomoedas (geralmente sempre abertas):**
- ✅ BTCUSD
- ✅ ETHUSD
- ✅ LTCUSD

---

## 🔄 Exemplo de Configuração Completa

```python
# bot_iqoption.py

# Linha ~43 - Ativo BASE (sem OTC)
self.ativo_base = "EURUSD"

# Linha ~47 - OTC Automático
self.usar_otc_automatico = True

# Linha ~44 - Timeframe
self.timeframe = 1  # 1 minuto

# Linha ~45 - Valor
self.valor_operacao = 5.0  # $5 por trade
```

---

## 🚨 O que NÃO fazer

❌ **NÃO** coloque "-OTC" no `ativo_base`:
```python
self.ativo_base = "EURUSD-OTC"  # ❌ ERRADO!
```

❌ **NÃO** desative o OTC automático se quer operar 24h:
```python
self.usar_otc_automatico = False  # ❌ Vai falhar fora do horário
```

✅ **CORRETO:**
```python
self.ativo_base = "EURUSD"  # ✅ SEM -OTC
self.usar_otc_automatico = True  # ✅ Detecta e usa automaticamente
```

---

## 💡 Dicas Finais

1. **Teste em DEMO primeiro** com `self.modo_pratica = True`
2. **Monitore os logs** para ver quando o bot muda para OTC
3. **OTC é normal** - não é erro, é o mercado 24h
4. **Criptomoedas** costumam estar sempre disponíveis (sem precisar de OTC)
5. **Fim de semana** sempre usará OTC para FOREX

---

## 📝 Logs para Entender

### ✅ **Funcionando Corretamente:**
```
📊 EST 3: Abrindo COMPRA | RSI: 24.87
🔄 Mercado aberto - Usando EURUSD
📈 Abrindo posição CALL
⚠️ Ativo suspenso! Tentando com EURUSD-OTC...
✅ Binary Option OTC executada | ID: 123456
✅ Posição CALL aberta | ID: 123456
```

### ❌ **Problema de Configuração:**
```
📈 Abrindo posição CALL
   Ativo: EURUSD-OTC-OTC | ...  ← ERRO: OTC duplicado!
```
→ **Solução**: Remova "-OTC" do `ativo_base`

---

## 🆘 Ainda com problemas?

1. Pare o bot (Ctrl+C)
2. Edite `bot_iqoption.py`:
   ```python
   self.ativo_base = "EURUSD"  # Sem -OTC
   self.usar_otc_automatico = True
   ```
3. Execute novamente:
   ```bash
   python bot_iqoption.py
   ```
4. Verifique os logs para confirmar que está usando OTC quando necessário

---

**✅ Agora seu bot detectará automaticamente ativos suspensos e usará OTC!** 🚀
