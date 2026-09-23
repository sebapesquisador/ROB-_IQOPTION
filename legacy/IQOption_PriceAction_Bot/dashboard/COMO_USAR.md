# 🚀 COMO USAR O PAINEL - GUIA RÁPIDO

## ⚡ Método Mais Fácil (Clique Duplo)

### 1️⃣ Iniciar o Painel
**Clique duas vezes** no arquivo:
```
START_PAINEL.bat
```
→ Uma nova janela abrirá com o servidor rodando
→ **NÃO FECHE** essa janela enquanto quiser usar o painel
→ O navegador pode abrir automaticamente em: http://127.0.0.1:5001

### 2️⃣ Testar o Painel (Opcional)
Com o painel rodando, **clique duas vezes** em:
```
TESTAR_PAINEL.bat
```
→ Envia dados de exemplo para você ver o painel funcionando

---

## 🔄 Usando PowerShell (Alternativa)

### Opção A - Abrir em nova janela:
```powershell
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard; python app.py"
```

### Opção B - Abrir 2 terminais:
**Terminal 1** (deixa rodando):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python app.py
```

**Terminal 2** (novo terminal para comandos):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python update_example.py
```

---

## 🤖 Integração com o Bot

### 1️⃣ Inicie o PAINEL primeiro:
- Clique duas vezes em `START_PAINEL.bat`
- Aguarde aparecer: "Running on http://127.0.0.1:5001"

### 2️⃣ Abra o navegador:
- http://127.0.0.1:5001

### 3️⃣ Execute o BOT (em outro terminal ou nova janela):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot
python bot_iqoption.py
```

→ O bot **automaticamente** enviará atualizações para o painel!
→ Você verá trades aparecendo em tempo real no navegador

---

## 📊 O que você verá no painel:

✅ **Ativo atual** (ex: EURUSD)
✅ **Timeframe** (ex: 5m)
✅ **Estratégia** (ex: 3)
✅ **Lucro Diário** (verde)
✅ **Lucro Total** (laranja)
✅ **Win Rate** (%)
✅ **Gráfico de lucro** ao longo do tempo
✅ **Últimos 10 trades** na tabela
✅ **Notificações** quando novos trades acontecem

---

## 🛑 Como Parar

### Parar o Painel:
- Vá na janela onde está rodando `app.py`
- Pressione `Ctrl + C`
- Ou feche a janela

### Parar o Bot:
- Vá no terminal do bot
- Pressione `Ctrl + C`

---

## 💡 Dicas Importantes

1. **Sempre inicie o PAINEL primeiro**, depois o bot
2. **Mantenha a janela do painel aberta** enquanto estiver usando
3. **O navegador atualiza sozinho** a cada 2 segundos
4. **Você pode abrir em vários navegadores** ao mesmo tempo
5. **Os dados persistem** mesmo se fechar o navegador (enquanto o servidor estiver rodando)

---

## 🔧 Resetar Dados

### Pelo Painel (Navegador):
- Clique em **"Zerar Lucro Diário"** ou **"Zerar Lucro Total"**

### Manualmente:
- Feche o servidor (Ctrl+C)
- Delete os arquivos:
  - `state.json` (zera tudo)
  - `history.json` (zera histórico de trades)
- Inicie o servidor novamente

---

## 🆘 Problemas Comuns

### "Impossível conectar ao servidor remoto"
→ O painel não está rodando!
→ Solução: Execute `START_PAINEL.bat` primeiro

### "Address already in use"
→ O painel já está rodando em outra janela
→ Solução: Feche a outra janela ou use a que já está aberta

### Painel não atualiza
→ Verifique se o bot está configurado com `dashboard_enabled = True`
→ Verifique se ambos (painel e bot) estão rodando

---

## ✅ Checklist de Sucesso

- [ ] Cliquei em `START_PAINEL.bat` ou rodei `python app.py`
- [ ] Vi a mensagem "Running on http://127.0.0.1:5001"
- [ ] Abri http://127.0.0.1:5001 no navegador
- [ ] Vejo o painel carregado (mesmo com valores zerados)
- [ ] (Opcional) Testei com `TESTAR_PAINEL.bat`
- [ ] Iniciei o bot em outro terminal/janela
- [ ] Vejo dados atualizando no painel

---

**Pronto! Agora você tem um painel profissional funcionando! 🎨📊✨**
