# 🚀 GUIA COMPLETO - BOT + PAINEL IQ OPTION

## 📋 PRÉ-REQUISITOS

### 1. Python Instalado
- Python 3.8 ou superior
- Verifique: `python --version`

### 2. Dependências Instaladas
Execute no PowerShell:

```powershell
pip install flask requests pandas numpy iqoptionapi
```

---

## 🎯 PASSO A PASSO COMPLETO

### PASSO 1: Instalar Dependências (Primeira Vez)

Abra o PowerShell e execute:

```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot
pip install -r requirements.txt
pip install flask requests
```

---

### PASSO 2: Configurar o Bot

Edite o arquivo `bot_iqoption.py` (linhas 39-40):

```python
self.email = "seu_email@exemplo.com"      # ← COLOQUE SEU EMAIL AQUI
self.senha = "SUA_SENHA_AQUI"             # ← COLOQUE SUA SENHA AQUI
```

Outras configurações importantes (linhas 43-48):

```python
self.estrategia_escolhida = 3             # Estratégia 1 a 11
self.ativo_base = "EURUSD"                # Par de moedas
self.timeframe = 5                        # Tempo do candle (minutos)
self.valor_operacao = 5.0                 # Valor em $ por operação
self.modo_pratica = True                  # True = DEMO | False = REAL
self.usar_otc_automatico = True           # Usa OTC automaticamente
```

---

### PASSO 3: Iniciar o Painel (SEMPRE PRIMEIRO!)

**Abra um PowerShell (Terminal 1)** e execute:

```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python app.py
```

**Você verá:**
```
============================================================
🚀 PAINEL IQ OPTION INICIADO
============================================================
📊 Dashboard: http://127.0.0.1:5001
 * Running on http://127.0.0.1:5001
```

**DEIXE ESSE TERMINAL ABERTO!** ✅

---

### PASSO 4: Abrir o Painel no Navegador

Abra qualquer navegador e acesse:

```
http://127.0.0.1:5001
```

Você verá o painel bonito e colorido! 🎨

---

### PASSO 5: Iniciar o Bot

**Abra OUTRO PowerShell (Terminal 2 - NOVO!)** e execute:

```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot
python bot_iqoption.py
```

**Você verá:**
```
============================================================
INICIANDO CONEXÃO COM IQ OPTION
============================================================
✅ Conectado com sucesso!
📊 Saldo na conta DEMO: $10,000.00
🤖 Bot ativo! Aguardando sinais...
```

---

### PASSO 6: Monitorar

**Agora você tem:**
- ✅ Terminal 1: Painel rodando (dashboard)
- ✅ Terminal 2: Bot rodando (trading)
- ✅ Navegador: Visualizando dados em tempo real

**O bot enviará atualizações automaticamente para o painel!** 📊✨

---

## 🖥️ RESUMO DOS COMANDOS

### Terminal 1 - Painel (Iniciar primeiro):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python app.py
```

### Terminal 2 - Bot (Iniciar depois):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot
python bot_iqoption.py
```

### Navegador:
```
http://127.0.0.1:5001
```

---

## 🛑 COMO PARAR

### Parar o Painel (Terminal 1):
- Pressione `Ctrl + C`

### Parar o Bot (Terminal 2):
- Pressione `Ctrl + C`

---

## 🔧 CONFIGURAÇÕES IMPORTANTES

### No arquivo `bot_iqoption.py`:

| Configuração | Linha | Descrição | Exemplo |
|-------------|-------|-----------|---------|
| Email | 39 | Seu email da IQ Option | `"seu@email.com"` |
| Senha | 40 | Sua senha da IQ Option | `"suaSenha123"` |
| Estratégia | 43 | Qual estratégia usar (1-11) | `3` |
| Ativo | 44 | Par de moedas | `"EURUSD"` |
| Timeframe | 45 | Tempo dos candles (min) | `5` |
| Valor | 46 | $ por operação | `5.0` |
| Modo | 47 | DEMO ou REAL | `True` = DEMO |
| Painel | 124 | Ativar/desativar painel | `True` = Ativo |

---

## 📊 O QUE O PAINEL MOSTRA

- ✅ **Ativo atual** (EURUSD, BTCUSD, etc)
- ✅ **Timeframe** (1m, 5m, 15m, etc)
- ✅ **Estratégia ativa** (1 a 11)
- ✅ **Lucro Diário** (verde)
- ✅ **Lucro Total** (laranja)
- ✅ **Win Rate** (%)
- ✅ **Gráfico de evolução** do lucro
- ✅ **Gráfico Win/Loss** (pizza)
- ✅ **Últimos 10 trades** (tabela)
- ✅ **Notificações** de novos trades

---

## 🧪 TESTAR SEM BOT (Dados Fake)

Se quiser testar o painel antes de rodar o bot:

**Terminal 1 - Painel:**
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python app.py
```

**Terminal 2 - Teste:**
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python update_example.py
```

Você verá dados de exemplo aparecerem no painel! 📊

---

## ⚠️ PROBLEMAS COMUNS

### "Impossível conectar ao servidor remoto"
→ O painel não está rodando
→ **Solução:** Execute o Terminal 1 primeiro (painel)

### "ModuleNotFoundError: No module named 'flask'"
→ Flask não está instalado
→ **Solução:** `pip install flask requests`

### "ModuleNotFoundError: No module named 'iqoptionapi'"
→ IQ Option API não instalada
→ **Solução:** `pip install iqoptionapi`

### Bot não conecta na IQ Option
→ Email ou senha incorretos
→ **Solução:** Verifique linhas 39-40 do `bot_iqoption.py`

### Painel não atualiza
→ Bot não está rodando OU `dashboard_enabled = False`
→ **Solução:** Inicie o bot E verifique linha 124 do código

---

## ✅ CHECKLIST DE SUCESSO

- [ ] Python instalado e funcionando
- [ ] Dependências instaladas (`pip install flask requests iqoptionapi pandas numpy`)
- [ ] Email e senha configurados no `bot_iqoption.py`
- [ ] Terminal 1: Painel rodando (`python app.py`)
- [ ] Navegador: http://127.0.0.1:5001 aberto
- [ ] Painel carregado e bonito
- [ ] Terminal 2: Bot rodando (`python bot_iqoption.py`)
- [ ] Bot conectou na IQ Option
- [ ] Painel atualizando automaticamente

---

## 🎯 ORDEM CORRETA DE EXECUÇÃO

```
1. Instalar dependências (primeira vez)
   ↓
2. Configurar bot_iqoption.py (email/senha)
   ↓
3. Abrir Terminal 1 → Iniciar painel
   ↓
4. Abrir navegador → http://127.0.0.1:5001
   ↓
5. Abrir Terminal 2 → Iniciar bot
   ↓
6. Monitorar no navegador! 🎉
```

---

## 💡 DICAS EXTRAS

1. **Use conta DEMO primeiro** para testar
2. **Deixe o navegador aberto** em tela secundária
3. **Monitore os logs** nos terminais
4. **Use Ctrl+C** para parar com segurança
5. **Feche o bot antes do painel** ao finalizar

---

## 📱 ACESSO DE OUTROS DISPOSITIVOS

Se quiser acessar o painel de outro computador/celular na mesma rede:

1. Descubra seu IP local:
   ```powershell
   ipconfig
   ```
   Procure por "IPv4" (ex: 192.168.15.8)

2. No outro dispositivo, acesse:
   ```
   http://192.168.15.8:5001
   ```

---

## 🆘 SUPORTE RÁPIDO

**Erro ao iniciar painel:**
```powershell
pip install --upgrade flask requests
```

**Erro ao iniciar bot:**
```powershell
pip install --upgrade iqoptionapi pandas numpy
```

**Resetar tudo:**
1. Feche painel e bot (Ctrl+C)
2. Delete `dashboard/state.json` e `dashboard/history.json`
3. Reinicie painel e bot

---

**✅ AGORA VOCÊ TEM TUDO PARA COMEÇAR! 🚀📊🎨**

Qualquer problema, execute os comandos acima na ordem e verifique o checklist!
