# 🎨 PAINEL WEB PROFISSIONAL - IQ OPTION BOT

## 🚀 INÍCIO RÁPIDO (2 PASSOS)

### 1️⃣ Inicie o Painel
Vá para a pasta `dashboard` e **clique duas vezes** em:
```
START_PAINEL.bat
```
→ Uma janela abrirá. **Deixe ela aberta!**

### 2️⃣ Abra no Navegador
```
http://127.0.0.1:5001
```

**PRONTO!** ✅

---

## 📁 Estrutura do Painel

```
dashboard/
├── START_PAINEL.bat      ← 🎯 CLIQUE AQUI para iniciar
├── TESTAR_PAINEL.bat     ← Enviar dados de teste
├── COMO_USAR.md          ← Guia completo
├── README_DASHBOARD.md   ← Documentação técnica
├── app.py                ← Servidor (não mexa)
├── state.json            ← Dados atuais
└── history.json          ← Histórico de trades
```

---

## 🤖 Como Integrar com o Bot

O bot **JÁ ESTÁ INTEGRADO** automaticamente! Basta:

1. **Iniciar o painel** (`START_PAINEL.bat`)
2. **Abrir outro terminal** e rodar:
   ```powershell
   python bot_iqoption.py
   ```
3. **Assistir no navegador** (http://127.0.0.1:5001)

---

## ✨ O Que o Painel Mostra

| Feature | Descrição |
|---------|-----------|
| 📊 **Ativo** | Par sendo negociado (EURUSD, BTCUSD, etc) |
| ⏰ **Timeframe** | Tempo dos candles (1m, 5m, 15m, etc) |
| 🧠 **Estratégia** | Qual estratégia está ativa (1-11) |
| 💚 **Lucro Diário** | Quanto você ganhou/perdeu hoje |
| 🧡 **Lucro Total** | Lucro acumulado total |
| 🏆 **Win Rate** | % de trades vencedores |
| 📈 **Gráfico de Lucro** | Evolução do lucro ao longo do tempo |
| 📋 **Últimos Trades** | Tabela com os 10 últimos trades |
| 🔔 **Notificações** | Pop-up quando novos trades acontecem |

---

## 🎨 Visual do Painel

- ✅ **Tema escuro elegante** com gradientes
- ✅ **Cards coloridos** com animações suaves
- ✅ **Gráficos interativos** (Chart.js)
- ✅ **Responsivo** (funciona em celular/tablet)
- ✅ **Atualização automática** a cada 2 segundos
- ✅ **Ícones profissionais** (Font Awesome)

---

## 🛠️ Comandos Úteis

### Iniciar Painel (Windows):
```powershell
cd dashboard
START_PAINEL.bat
```

### Iniciar Painel (PowerShell manual):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot\dashboard
python app.py
```

### Testar Painel (enviar dados fake):
```powershell
cd dashboard
TESTAR_PAINEL.bat
```

### Iniciar Bot (em OUTRO terminal):
```powershell
cd C:\Users\dinha\Music\IQOption_PriceAction_Bot
python bot_iqoption.py
```

---

## 🔧 Resetar Dados

### Via Navegador:
- Clique em **"Zerar Lucro Diário"** (botão amarelo)
- Clique em **"Zerar Lucro Total"** (botão vermelho)

### Via Arquivos:
1. Feche o painel (Ctrl+C)
2. Delete `state.json` e/ou `history.json`
3. Reinicie o painel

---

## 📖 Documentação Completa

- **Guia de Uso**: `dashboard/COMO_USAR.md`
- **Documentação Técnica**: `dashboard/README_DASHBOARD.md`
- **Problemas**: Veja seção "Solução de Problemas" nos arquivos acima

---

## 🎯 Checklist Rápido

- [ ] Executei `dashboard/START_PAINEL.bat`
- [ ] Vi "Running on http://127.0.0.1:5001"
- [ ] Abri http://127.0.0.1:5001 no navegador
- [ ] Vejo o painel carregado (bonito e colorido)
- [ ] Executei o bot em outra janela
- [ ] Vejo dados atualizando automaticamente

---

## 💡 Dica de Ouro

**Deixe o navegador aberto em uma tela secundária** (se tiver) e acompanhe seus trades em tempo real enquanto faz outras coisas! 🖥️📊

---

## 🆘 Ajuda Rápida

**Problema**: "Impossível conectar ao servidor remoto"
→ **Solução**: O painel não está rodando. Execute `START_PAINEL.bat` primeiro.

**Problema**: "Address already in use"
→ **Solução**: O painel já está rodando. Procure a janela ou feche e reabra.

**Problema**: Painel não mostra dados do bot
→ **Solução**: Certifique-se que o bot está rodando E que `dashboard_enabled = True` no código.

---

**✅ Painel criado com excelência e pronto para usar! 🎨🚀📊**

Qualquer dúvida, veja: `dashboard/COMO_USAR.md`
