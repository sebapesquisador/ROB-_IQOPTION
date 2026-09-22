# 🎨 Painel Web Profissional - IQ Option Bot

Dashboard completo e bonito para monitorar seu bot IQ Option em tempo real!

## ✨ Funcionalidades

### 📊 Visualização em Tempo Real
- ✅ Ativo atual, Timeframe e Estratégia
- ✅ Lucro Diário e Lucro Total
- ✅ Win Rate com gráfico pizza
- ✅ Gráfico de histórico de lucro acumulado
- ✅ Tabela com últimos 10 trades
- ✅ Notificações de trades em tempo real
- ✅ Atualização automática a cada 2 segundos

### 🎨 Design Profissional
- ✅ Interface moderna com Bootstrap 5
- ✅ Tema escuro elegante com gradientes
- ✅ Animações suaves e transições
- ✅ Cards com hover effects
- ✅ Ícones Font Awesome
- ✅ Gráficos interativos (Chart.js)
- ✅ Totalmente responsivo

### 🔧 Funcionalidades Extras
- ✅ Botões para zerar lucro diário/total
- ✅ Toast notifications para novos trades
- ✅ Histórico de até 100 trades
- ✅ Proteção opcional por API Key

---

## 🚀 Instalação Rápida

### 1️⃣ Instalar dependências

```powershell
pip install flask requests
```

### 2️⃣ Iniciar o painel (3 opções)

**Opção A - Script automático (RECOMENDADO):**
```powershell
python dashboard/start_dashboard.py
```
→ Abre automaticamente no navegador!

**Opção B - Manual:**
```powershell
cd dashboard
python app.py
```

**Opção C - Background (PowerShell):**
```powershell
Start-Process python -ArgumentList "dashboard/app.py" -WindowStyle Hidden
```

### 3️⃣ Acessar o painel

Abra no navegador: **http://127.0.0.1:5001**

---

## 🔌 Integração com o Bot

O bot `bot_iqoption.py` **JÁ ESTÁ INTEGRADO** automaticamente!

Ele envia atualizações para o painel:
- ✅ Após cada trade executado
- ✅ Quando lucros são atualizados
- ✅ Informações de ativo, timeframe e estratégia

### Como funciona:

O bot chama estas funções automaticamente:

```python
# Atualiza estado geral
self.atualizar_painel()

# Envia trade individual ao histórico
self.enviar_trade_ao_painel(
    direcao="CALL",
    resultado="WIN",
    lucro=15.50,
    preco=1.08523
)
```

### Desabilitar painel (se necessário):

No `bot_iqoption.py`, linha ~124:

```python
self.dashboard_enabled = False  # Desativa integração
```

---

## 📡 Endpoints da API

### GET `/`
Retorna o dashboard HTML

### GET `/state`
Retorna JSON com estado atual:
```json
{
  "ativo": "EURUSD",
  "timeframe": "5m",
  "estrategia": "3",
  "lucro_diario": 12.50,
  "lucro_total": 150.75,
  "winrate": 60.0,
  "total_trades": 25,
  "wins": 15,
  "updated_at": "2025-11-07T12:30:00Z"
}
```

### GET `/history`
Retorna array com últimos 100 trades:
```json
[
  {
    "timestamp": "2025-11-07T12:25:00",
    "ativo": "EURUSD",
    "direcao": "CALL",
    "resultado": "WIN",
    "lucro": 15.50,
    "preco": 1.08523
  }
]
```

### POST `/update`
Atualiza o estado (usado pelo bot):
```json
{
  "ativo": "EURUSD",
  "timeframe": "5m",
  "estrategia": "3",
  "lucro_diario": 12.50,
  "lucro_total": 150.75,
  "total_trades": 25,
  "wins": 15
}
```

### POST `/add_trade`
Adiciona trade ao histórico:
```json
{
  "timestamp": "2025-11-07T12:25:00",
  "ativo": "EURUSD",
  "direcao": "CALL",
  "resultado": "WIN",
  "lucro": 15.50,
  "preco": 1.08523
}
```

### POST `/reset_daily`
Zera lucro diário

### POST `/reset_total`
Zera lucro total

---

## 🔐 Proteção com API Key (Opcional)

Se quiser proteger os endpoints POST:

### 1️⃣ Defina a variável de ambiente:

**PowerShell:**
```powershell
$env:DASHBOARD_API_KEY = "minha_chave_secreta_123"
python dashboard/app.py
```

**CMD:**
```cmd
set DASHBOARD_API_KEY=minha_chave_secreta_123
python dashboard/app.py
```

### 2️⃣ Configure no bot:

No `bot_iqoption.py`, adicione após a linha ~124:

```python
self.dashboard_api_key = "minha_chave_secreta_123"
```

E atualize as funções para incluir o header:

```python
headers = {"X-API-KEY": self.dashboard_api_key} if hasattr(self, 'dashboard_api_key') else {}
requests.post(url, json=payload, headers=headers, timeout=2)
```

---

## 🎯 Teste Manual (sem bot)

Para testar o painel sem rodar o bot:

```powershell
# 1. Inicie o painel
python dashboard/app.py

# 2. Em outro terminal, envie update de teste
python dashboard/update_example.py
```

Ou via PowerShell:

```powershell
$body = @{
    ativo = "EURUSD"
    timeframe = "5m"
    estrategia = "3"
    lucro_diario = 25.50
    lucro_total = 200.00
    total_trades = 30
    wins = 18
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:5001/update -Method POST -Body $body -ContentType "application/json"
```

---

## 🎨 Capturas de Tela

### Dashboard Principal
- Cards coloridos para Ativo, Timeframe, Estratégia, Win Rate
- Lucro Diário (verde) e Lucro Total (laranja) em destaque
- Gráfico de linha mostrando evolução do lucro
- Gráfico pizza Win/Loss

### Tabela de Trades
- Últimos 10 trades com horário, ativo, direção, resultado e lucro
- Badges coloridos (verde = WIN, vermelho = LOSS)
- Ícones indicando direção (↑ CALL, ↓ PUT)

### Notificações
- Toast notification aparece automaticamente quando novo trade é executado
- Mostra se foi WIN ou LOSS com ícone e cores

---

## 🛠️ Solução de Problemas

### Painel não abre
```powershell
# Verifique se Flask está instalado
pip show flask

# Se não estiver, instale
pip install flask requests
```

### Erro "Address already in use"
```powershell
# A porta 5001 já está em uso, pare o processo
# Windows:
netstat -ano | findstr :5001
taskkill /PID <PID> /F

# Ou mude a porta no app.py (última linha):
app.run(host="0.0.0.0", port=5002)
```

### Bot não atualiza o painel
```powershell
# 1. Verifique se o painel está rodando
curl http://127.0.0.1:5001/health

# 2. Verifique se dashboard_enabled = True no bot
# Linha ~124 do bot_iqoption.py

# 3. Veja logs do bot para erros de conexão
```

### Gráficos não aparecem
```powershell
# Verifique conexão com internet (Chart.js é carregado via CDN)
# Ou baixe Chart.js localmente e ajuste o HTML
```

---

## 📂 Estrutura de Arquivos

```
dashboard/
├── app.py                  # Servidor Flask (backend)
├── start_dashboard.py      # Script de inicialização automática
├── state.json              # Estado atual do bot
├── history.json            # Histórico de trades (últimos 100)
├── templates/
│   └── index.html          # Interface HTML do painel
├── static/
│   ├── style.css           # Estilos CSS customizados
│   └── dashboard.js        # JavaScript (gráficos, atualizações)
├── update_example.py       # Exemplo de atualização manual
└── README_DASHBOARD.md     # Esta documentação
```

---

## 🚀 Próximos Passos

1. **Inicie o painel**: `python dashboard/start_dashboard.py`
2. **Inicie o bot**: `python bot_iqoption.py`
3. **Abra o navegador**: http://127.0.0.1:5001
4. **Monitore em tempo real!** 📊

---

## 💡 Dicas Extras

- 📱 **Acesso remoto**: Mude `0.0.0.0` para seu IP local e acesse de outros dispositivos na rede
- 🔒 **Segurança**: Use API Key se expor o painel na internet
- 📊 **Histórico**: O painel mantém os últimos 100 trades automaticamente
- 🎨 **Personalização**: Edite `style.css` para mudar cores e estilos
- 📈 **Gráficos**: Adicione mais gráficos editando `dashboard.js` e `index.html`

---

## ⚠️ Notas Importantes

- O painel roda **localmente** por padrão (127.0.0.1)
- Os dados são salvos em **JSON** (state.json e history.json)
- Ao reiniciar o servidor, os dados **persistem**
- Para limpar histórico: delete `history.json`
- Para resetar estado: delete `state.json`

---

## 🆘 Suporte

Se tiver problemas:
1. Verifique se Flask está instalado (`pip show flask`)
2. Veja os logs do terminal onde rodou `app.py`
3. Teste manualmente com `update_example.py`
4. Verifique se a porta 5001 não está bloqueada pelo firewall

---

**✅ Painel criado com excelência! Aproveite! 🎨📊🚀**
