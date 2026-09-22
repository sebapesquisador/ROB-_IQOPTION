/* Painel de controle — usa apenas URLs relativas (funciona atrás de proxy) */
'use strict';

const $ = (id) => document.getElementById(id);
const fmtMoney = (v) => (v == null || isNaN(v) ? '—' :
  (v < 0 ? '-' : '') + '$' + Math.abs(v).toFixed(2));
const fmtPct = (v) => (v == null || isNaN(v) ? '—' : v.toFixed(1) + '%');
const cls = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : 'neutral');

let equityChart, priceChart, config = null, lastState = null;

/* ---------------- HTTP ---------------- */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function toast(msg, kind = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $('toast-host').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------------- Gráficos ---------------- */
function initCharts() {
  const gridColor = 'rgba(36,44,59,.55)';
  const tickColor = '#8b98ad';
  const baseScales = {
    x: { grid: { color: gridColor }, ticks: { color: tickColor, maxTicksLimit: 8, font: { size: 10 } } },
    y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10 } } },
  };

  equityChart = new Chart($('equityChart'), {
    type: 'line',
    data: { labels: [], datasets: [{
      label: 'Saldo', data: [], borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,.12)', fill: true,
      tension: .3, pointRadius: 0, borderWidth: 2,
    }]},
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { ...baseScales, y: { ...baseScales.y, ticks: { ...baseScales.y.ticks, callback: (v) => '$' + v.toFixed(0) } } },
    },
  });

  priceChart = new Chart($('priceChart'), {
    type: 'line',
    data: { labels: [], datasets: [
      { label: 'Preço', data: [], borderColor: '#e6edf7', borderWidth: 1.8, pointRadius: 0, tension: .2 },
      { label: 'MA rápida', data: [], borderColor: '#22c55e', borderWidth: 1.2, pointRadius: 0, tension: .2 },
      { label: 'MA lenta', data: [], borderColor: '#f59e0b', borderWidth: 1.2, pointRadius: 0, tension: .2 },
      { label: 'BB sup.', data: [], borderColor: 'rgba(139,92,246,.45)', borderWidth: 1, pointRadius: 0, borderDash: [4, 4] },
      { label: 'BB inf.', data: [], borderColor: 'rgba(139,92,246,.45)', borderWidth: 1, pointRadius: 0, borderDash: [4, 4] },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: tickColor, boxWidth: 10, font: { size: 10 } } } },
      scales: baseScales,
    },
  });
}

/* ---------------- Render ---------------- */
function renderStatus(s) {
  if (!s || !s.risk) return;
  lastState = s.state;
  const r = s.risk, st = r.stats || {};

  $('sub-broker').textContent =
    `${s.broker} · ${s.symbol} · ${s.timeframe_minutes}m · exp ${s.expiration_minutes}m · ${s.strategy}`;

  // Badges
  const modeBadge = $('mode-badge');
  const live = !s.dry_run && s.account_mode === 'real';
  modeBadge.textContent = live ? 'CONTA REAL' : (s.dry_run ? 'DRY-RUN' : 'DEMO');
  modeBadge.className = 'badge ' + (live ? 'badge-live' : 'badge-dry');

  const stateBadge = $('state-badge');
  const labels = { running: 'operando', paused: 'pausado', stopped: 'parado', halted: 'travado' };
  stateBadge.className = 'badge badge-' + s.state;
  $('state-text').textContent = labels[s.state] || s.state;

  $('btn-start').disabled = s.state === 'running';
  $('btn-pause').disabled = s.state !== 'running';
  $('btn-stop').disabled  = s.state === 'stopped';
  $('btn-pause').textContent = s.state === 'paused' ? 'Retomar' : 'Pausar';

  // KPIs
  $('kpi-balance').textContent = fmtMoney(r.balance);
  $('kpi-peak').textContent = 'pico ' + fmtMoney(r.equity_peak);

  const daily = $('kpi-daily');
  daily.textContent = fmtMoney(r.daily_pnl);
  daily.className = 'kpi-value ' + cls(r.daily_pnl);
  $('kpi-daily-trades').textContent =
    `${r.daily_trades} operações · ${r.daily_wins}V / ${r.daily_losses}D`;

  const wr = st.win_rate || 0;
  const wrEl = $('kpi-winrate');
  wrEl.textContent = fmtPct(wr);
  wrEl.className = 'kpi-value ' + (wr >= 54.05 ? 'pos' : wr > 0 ? 'neg' : 'neutral');

  const pf = st.profit_factor;
  const pfEl = $('kpi-pf');
  pfEl.textContent = pf == null ? '∞' : pf.toFixed(2);
  pfEl.className = 'kpi-value ' + ((pf == null || pf >= 1) ? 'pos' : 'neg');
  $('kpi-expectancy').textContent = 'expectativa ' + fmtMoney(st.expectancy);

  const ddEl = $('kpi-dd');
  ddEl.textContent = fmtPct(r.drawdown_pct);
  ddEl.className = 'kpi-value ' + (r.drawdown_pct > 10 ? 'neg' : 'neutral');
  const streak = st.current_streak || 0;
  $('kpi-streak').textContent = streak === 0 ? 'sequência —'
    : `sequência ${Math.abs(streak)} ${streak > 0 ? 'vitórias' : 'derrotas'}`;

  $('kpi-stake').textContent = fmtMoney(r.next_stake);
  $('kpi-open').textContent = `${s.open_orders} abertas`;

  // Consumo do limite diário
  const used = Math.min(100, r.daily_loss_used_pct || 0);
  const bar = $('loss-bar');
  bar.style.width = used + '%';
  bar.style.background = used > 80 ? 'var(--red)' : used > 50 ? 'var(--amber)' : 'var(--green)';
  $('loss-budget-text').textContent =
    `${used.toFixed(0)}% de ${fmtMoney(r.daily_loss_limit)} · meta ${fmtMoney(r.daily_target)}`;

  // Alerta
  const alert = $('risk-alert');
  if (s.state === 'halted') {
    alert.textContent = '⛔ Robô travado pela gestão de risco — limite diário, drawdown ou meta atingidos. Revise antes de retomar.';
    alert.classList.remove('hidden');
  } else if (r.halted_until) {
    alert.textContent = '⏸ Em cooldown após sequência de derrotas até ' + new Date(r.halted_until).toLocaleTimeString('pt-BR');
    alert.classList.remove('hidden');
  } else {
    alert.classList.add('hidden');
  }

  renderSignal(s.last_signal);
}

function renderSignal(sig) {
  const dirEl = $('signal-dir');
  if (!sig || sig.direction === 'NONE') {
    dirEl.textContent = 'AGUARDANDO';
    dirEl.className = 'signal-dir';
    $('signal-reason').textContent = sig ? sig.reason : '—';
    $('conf-fill').style.width = '0%';
    $('conf-value').textContent = '—';
    $('signal-indicators').innerHTML = '';
    return;
  }
  dirEl.textContent = sig.direction === 'CALL' ? '▲ COMPRA' : '▼ VENDA';
  dirEl.className = 'signal-dir ' + sig.direction.toLowerCase();
  $('signal-reason').textContent = sig.reason;
  $('conf-fill').style.width = (sig.confidence * 100) + '%';
  $('conf-value').textContent = (sig.confidence * 100).toFixed(0) + '%';
  $('signal-indicators').innerHTML = Object.entries(sig.indicators || {})
    .map(([k, v]) => `<span class="chip">${k} <b>${typeof v === 'number' ? v.toFixed(2) : v}</b></span>`)
    .join('');
}

function renderTrades(trades) {
  const body = $('trades-body');
  $('trades-count').textContent = `${trades.length} registros`;
  if (!trades.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">Nenhuma operação ainda</td></tr>';
    return;
  }
  body.innerHTML = trades.map((t) => {
    const time = new Date(t.opened_at).toLocaleTimeString('pt-BR');
    const conf = t.confidence != null ? (t.confidence * 100).toFixed(0) + '%' : '—';
    return `<tr>
      <td>${time}</td>
      <td>${t.symbol}</td>
      <td><span class="pill pill-${t.direction.toLowerCase()}">${t.direction}</span></td>
      <td>${fmtMoney(t.amount)}</td>
      <td>${t.strategy || '—'}</td>
      <td>${conf}</td>
      <td><span class="pill pill-${t.status}">${t.status}</span></td>
      <td class="${cls(t.profit)}">${fmtMoney(t.profit)}</td>
    </tr>`;
  }).join('');
}

function renderEvents(events) {
  $('events-list').innerHTML = events.length
    ? events.map((e) => `
        <div class="event ${e.level}">
          <div class="event-time">${new Date(e.ts).toLocaleTimeString('pt-BR')} · ${e.category}</div>
          <div class="event-msg">${e.message}</div>
        </div>`).join('')
    : '<div class="muted">Nenhum evento</div>';
}

function renderBacktest(data) {
  const box = $('bt-results');
  box.innerHTML = `<div class="muted">Equilíbrio com payout ${data.payout}: <b>${data.breakeven_win_rate}%</b> de acerto</div>` +
    data.results.map((r) => {
      if (r.error) return `<div class="bt-card rejected"><div class="bt-name">${r.strategy}</div><div class="bt-verdict">erro: ${r.error}</div></div>`;
      const v = r.verdict || '';
      const kind = v.startsWith('APROVADA') ? 'approved'
        : (v.startsWith('REPROVADA') ? 'rejected' : 'marginal');
      return `<div class="bt-card ${kind}">
        <div class="bt-head">
          <span class="bt-name">${r.strategy}</span>
          <span class="${cls(r.net_profit)}">${fmtMoney(r.net_profit)}</span>
        </div>
        <div class="bt-metrics">
          <span>acerto <b>${r.win_rate}%</b></span>
          <span>vantagem <b class="${cls(r.edge_pp)}">${r.edge_pp > 0 ? '+' : ''}${r.edge_pp}pp</b></span>
          <span>trades <b>${r.total_trades}</b></span>
          <span>PF <b>${r.profit_factor ?? '∞'}</b></span>
          <span>DD <b>${r.max_drawdown_pct}%</b></span>
        </div>
        <div class="bt-verdict muted">${v}</div>
      </div>`;
    }).join('');
}

/* ---------------- Carregamento ---------------- */
async function loadConfig() {
  config = await api('/api/config');
  const sel = $('cfg-strategy');
  sel.innerHTML = config.strategies_available
    .map((s) => `<option value="${s.name}">${s.name}</option>`).join('');
  sel.value = config.strategy;
  $('cfg-symbol').value = config.symbol;
  $('cfg-timeframe').value = config.timeframe_minutes;
  $('cfg-expiration').value = config.expiration_minutes;
  $('cfg-dryrun').checked = config.dry_run;
  $('cfg-confidence').value = config.strategy_params.min_confidence;
  $('conf-label').textContent = config.strategy_params.min_confidence;
  $('cfg-stake').value = config.risk.percent_stake;
  $('cfg-maxloss').value = config.risk.max_daily_loss_pct;
}

async function loadPerformance() {
  const p = await api('/api/performance');
  const curve = p.equity_curve || [];
  equityChart.data.labels = curve.map((c) => new Date(c.ts).toLocaleTimeString('pt-BR'));
  equityChart.data.datasets[0].data = curve.map((c) => c.balance);
  equityChart.update('none');
}

async function loadCandles() {
  try {
    const d = await api('/api/candles?limit=120');
    $('candle-symbol').textContent = `${d.symbol} · ${d.timeframe}m`;
    const c = d.candles;
    priceChart.data.labels = c.map((x) => new Date(x.time).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
    priceChart.data.datasets[0].data = c.map((x) => x.close);
    priceChart.data.datasets[1].data = c.map((x) => x.ma_fast);
    priceChart.data.datasets[2].data = c.map((x) => x.ma_slow);
    priceChart.data.datasets[3].data = c.map((x) => x.bb_upper);
    priceChart.data.datasets[4].data = c.map((x) => x.bb_lower);
    priceChart.update('none');
  } catch (e) { /* corretora pode estar desconectada */ }
}

async function loadTables() {
  try {
    const [trades, events] = await Promise.all([
      api('/api/trades?limit=50'), api('/api/events?limit=40'),
    ]);
    renderTrades(trades);
    renderEvents(events);
  } catch (e) { /* silencioso */ }
}

/* ---------------- SSE ---------------- */
function connectStream() {
  const es = new EventSource('/api/stream');
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.event === 'status') {
      renderStatus(msg.data);
    } else if (msg.event === 'order_opened') {
      toast(`Ordem aberta: ${msg.data.direction} ${fmtMoney(msg.data.amount)}`, 'info');
      loadTables();
    } else if (msg.event === 'order_closed') {
      const won = msg.data.status === 'won';
      toast(`${won ? '✔' : '✖'} ${msg.data.status.toUpperCase()} · ${fmtMoney(msg.data.profit)}`,
            won ? 'ok' : 'err');
      loadTables();
      loadPerformance();
    }
  };
  es.onerror = () => { es.close(); setTimeout(connectStream, 5000); };
}

/* ---------------- Ações ---------------- */
function bindEvents() {
  $('btn-start').onclick = async () => {
    try { await api('/api/control/start', { method: 'POST' }); toast('Robô iniciado', 'ok'); }
    catch (e) { toast('Erro: ' + e.message, 'err'); }
  };
  $('btn-stop').onclick = async () => {
    try { await api('/api/control/stop', { method: 'POST' }); toast('Robô parado', 'info'); }
    catch (e) { toast('Erro: ' + e.message, 'err'); }
  };
  $('btn-pause').onclick = async () => {
    const action = lastState === 'paused' ? 'resume' : 'pause';
    try {
      await api(`/api/control/${action}`, { method: 'POST' });
      toast(action === 'pause' ? 'Pausado' : 'Retomado', 'info');
    } catch (e) { toast('Erro: ' + e.message, 'err'); }
  };

  $('cfg-confidence').oninput = (e) => { $('conf-label').textContent = e.target.value; };

  $('btn-save').onclick = async () => {
    const body = {
      symbol: $('cfg-symbol').value.trim().toUpperCase(),
      timeframe_minutes: +$('cfg-timeframe').value,
      expiration_minutes: +$('cfg-expiration').value,
      strategy: $('cfg-strategy').value,
      dry_run: $('cfg-dryrun').checked,
      min_confidence: +$('cfg-confidence').value,
      percent_stake: +$('cfg-stake').value,
      max_daily_loss_pct: +$('cfg-maxloss').value,
    };
    try {
      await api('/api/config', { method: 'PATCH', body: JSON.stringify(body) });
      toast('Configuração salva', 'ok');
      await loadConfig();
    } catch (e) { toast('Erro: ' + e.message, 'err'); }
  };

  $('btn-backtest').onclick = async () => {
    const btn = $('btn-backtest');
    btn.disabled = true; btn.textContent = 'Executando…';
    try {
      const data = await api('/api/backtest', {
        method: 'POST',
        body: JSON.stringify({
          candles: +$('bt-candles').value,
          payout: +$('bt-payout').value,
          min_confidence: +$('cfg-confidence').value,
        }),
      });
      renderBacktest(data);
      toast('Backtest concluído', 'ok');
    } catch (e) {
      toast('Erro no backtest: ' + e.message, 'err');
    } finally {
      btn.disabled = false; btn.textContent = 'Testar todas as estratégias';
    }
  };
}

/* ---------------- Boot ---------------- */
(async function init() {
  initCharts();
  bindEvents();
  try {
    await loadConfig();
    renderStatus(await api('/api/status'));
  } catch (e) { toast('Falha ao carregar: ' + e.message, 'err'); }
  await Promise.all([loadPerformance(), loadCandles(), loadTables()]);
  connectStream();
  setInterval(loadCandles, 30000);
  setInterval(loadPerformance, 20000);
})();
