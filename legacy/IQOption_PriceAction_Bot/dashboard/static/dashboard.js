// Dashboard JavaScript - IQ Option Bot
let winChart, profitChart;
let lastTradeCount = 0;

// Initialize Charts
function initCharts() {
  // Win/Loss Pie Chart
  const winCtx = document.getElementById('winChart').getContext('2d');
  winChart = new Chart(winCtx, {
    type: 'doughnut',
    data: {
      labels: ['Wins', 'Losses'],
      datasets: [{
        data: [0, 0],
        backgroundColor: ['#28a745', '#dc3545'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false }
      }
    }
  });

  // Profit History Line Chart
  const profitCtx = document.getElementById('profitChart').getContext('2d');
  profitChart = new Chart(profitCtx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Lucro Acumulado',
        data: [],
        borderColor: '#667eea',
        backgroundColor: 'rgba(102, 126, 234, 0.1)',
        fill: true,
        tension: 0.4,
        borderWidth: 3,
        pointRadius: 4,
        pointBackgroundColor: '#667eea'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.1)' },
          ticks: { color: '#fff', callback: value => '$' + value.toFixed(2) }
        },
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.1)' },
          ticks: { color: '#fff', maxTicksLimit: 10 }
        }
      },
      plugins: {
        legend: { labels: { color: '#fff' } }
      }
    }
  });
}

// Fetch State
async function fetchState() {
  try {
    const res = await fetch('/state');
    const state = await res.json();

    // Update basic info
    document.getElementById('ativo').innerText = state.ativo || '-';
    document.getElementById('timeframe').innerText = state.timeframe || '-';
    document.getElementById('estrategia').innerText = state.estrategia || '-';
    
    // Update profits with animation
    updateValue('lucro_diario', state.lucro_diario || 0, '$');
    updateValue('lucro_total', state.lucro_total || 0, '$');
    
    // Update winrate
    const winrate = state.winrate || 0;
    document.getElementById('winrate_text').innerText = winrate.toFixed(1) + '%';
    
    // Update timestamp
    document.getElementById('updated_at').innerText = new Date(state.updated_at).toLocaleString('pt-BR');

    // Update Win/Loss chart
    const wins = Number(state.wins || 0);
    const losses = Math.max(0, Number(state.total_trades || 0) - wins);
    winChart.data.datasets[0].data = [wins, losses];
    winChart.update('none');
    
    // Update counts
    document.getElementById('wins_count').innerText = wins;
    document.getElementById('losses_count').innerText = losses;

  } catch (e) {
    console.error('Erro ao buscar estado:', e);
  }
}

// Fetch History
async function fetchHistory() {
  try {
    const res = await fetch('/history');
    const history = await res.json();

    // Check for new trades
    if (history.length > lastTradeCount) {
      const newTrade = history[history.length - 1];
      showTradeNotification(newTrade);
      lastTradeCount = history.length;
    }

    // Update trades table
    const tbody = document.getElementById('trades_table');
    if (history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Aguardando trades...</td></tr>';
    } else {
      tbody.innerHTML = history.slice(-10).reverse().map(t => {
        const badge = t.resultado === 'WIN' ? 'bg-success' : 'bg-danger';
        const icon = t.resultado === 'WIN' ? 'fa-check' : 'fa-times';
        const dirIcon = t.direcao === 'CALL' ? 'fa-arrow-up text-success' : 'fa-arrow-down text-danger';
        const lucroColor = t.lucro >= 0 ? 'text-success' : 'text-danger';
        const time = new Date(t.timestamp).toLocaleTimeString('pt-BR');
        
        return `
          <tr>
            <td>${time}</td>
            <td><strong>${t.ativo}</strong></td>
            <td><i class="fas ${dirIcon} me-1"></i>${t.direcao}</td>
            <td><span class="badge ${badge}"><i class="fas ${icon} me-1"></i>${t.resultado}</span></td>
            <td class="${lucroColor} fw-bold">$${t.lucro.toFixed(2)}</td>
          </tr>
        `;
      }).join('');
    }

    // Update profit chart
    if (history.length > 0) {
      let accumulated = 0;
      const labels = [];
      const data = [];
      
      history.forEach((t, i) => {
        accumulated += t.lucro;
        labels.push(`#${i + 1}`);
        data.push(accumulated);
      });

      profitChart.data.labels = labels.slice(-20);
      profitChart.data.datasets[0].data = data.slice(-20);
      profitChart.update('none');
    }

  } catch (e) {
    console.error('Erro ao buscar histórico:', e);
  }
}

// Update value with animation
function updateValue(elementId, value, prefix = '') {
  const element = document.getElementById(elementId);
  const formatted = prefix + value.toFixed(2);
  
  if (element.innerText !== formatted) {
    element.style.transform = 'scale(1.1)';
    element.innerText = formatted;
    setTimeout(() => {
      element.style.transform = 'scale(1)';
    }, 200);
  }
}

// Show trade notification
function showTradeNotification(trade) {
  const toast = document.getElementById('tradeToast');
  const title = document.getElementById('toast-title');
  const body = document.getElementById('toast-body');
  const icon = document.getElementById('toast-icon');
  
  if (trade.resultado === 'WIN') {
    icon.className = 'fas fa-check-circle text-success me-2';
    title.innerText = '✅ Trade Vencedor!';
    body.innerText = `${trade.ativo} ${trade.direcao} • Lucro: $${trade.lucro.toFixed(2)}`;
    toast.classList.add('bg-success');
    toast.classList.remove('bg-danger');
  } else {
    icon.className = 'fas fa-times-circle text-danger me-2';
    title.innerText = '❌ Trade Perdedor';
    body.innerText = `${trade.ativo} ${trade.direcao} • Prejuízo: $${trade.lucro.toFixed(2)}`;
    toast.classList.add('bg-danger');
    toast.classList.remove('bg-success');
  }
  
  const bsToast = new bootstrap.Toast(toast);
  bsToast.show();
}

// Reset buttons
document.getElementById('btn-reset-daily').addEventListener('click', async () => {
  if (!confirm('Deseja realmente zerar o lucro diário?')) return;
  
  try {
    await fetch('/reset_daily', { method: 'POST' });
    await fetchState();
    alert('✅ Lucro diário zerado com sucesso!');
  } catch (e) {
    alert('❌ Erro ao zerar lucro diário');
  }
});

document.getElementById('btn-reset-total').addEventListener('click', async () => {
  if (!confirm('⚠️ ATENÇÃO: Deseja realmente zerar o lucro TOTAL?')) return;
  
  try {
    await fetch('/reset_total', { method: 'POST' });
    await fetchState();
    alert('✅ Lucro total zerado com sucesso!');
  } catch (e) {
    alert('❌ Erro ao zerar lucro total');
  }
});

// Initialize
initCharts();
fetchState();
fetchHistory();

// Auto-update every 2 seconds
setInterval(fetchState, 2000);
setInterval(fetchHistory, 3000);
