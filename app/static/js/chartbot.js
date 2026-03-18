// Chartbot JavaScript
// notification_days: 0=월, 1=화, 2=수, 3=목, 4=금, 5=토, 6=일 (Python weekday)
var DAY_LABELS = ['월', '화', '수', '목', '금', '토', '일'];

document.addEventListener('DOMContentLoaded', function() {
    loadChartbotStatus();
    loadChartbotSettings();
    loadTickers();
    loadLogs();

    const activeToggle = document.getElementById('chartbot-active-toggle');
    activeToggle.addEventListener('change', async function() {
        await toggleChartbotActive(this.checked);
    });

    var tickerInput = document.getElementById('ticker-input');
    var marketSelect = document.getElementById('market-select');
    if (tickerInput) {
        tickerInput.addEventListener('blur', updateAddTickerName);
        tickerInput.addEventListener('input', debounce(function() {
            var v = tickerInput.value.trim();
            if (v && /^\d{6}$/.test(v) && marketSelect && marketSelect.value === 'US') {
                marketSelect.value = 'KR';
            }
            updateAddTickerName();
        }, 500));
    }
    if (marketSelect) {
        marketSelect.addEventListener('change', updateAddTickerName);
    }
});

function debounce(fn, ms) {
    var timeout;
    return function() {
        var ctx = this, args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(function() { fn.apply(ctx, args); }, ms);
    };
}

async function updateAddTickerName() {
    var tickerInput = document.getElementById('ticker-input');
    var marketSelect = document.getElementById('market-select');
    var nameEl = document.getElementById('add-ticker-name');
    if (!tickerInput || !nameEl) return;

    var ticker = tickerInput.value.trim().toUpperCase();
    var market = marketSelect ? marketSelect.value : 'US';

    if (!ticker) {
        nameEl.textContent = '';
        return;
    }

    try {
        var data = await fetchApi('/api/chartbot/ticker-name?ticker=' + encodeURIComponent(ticker) + '&market=' + market);
        nameEl.textContent = data.name && data.name !== ticker ? data.name : '';
    } catch (e) {
        nameEl.textContent = '';
    }
}

async function loadChartbotStatus() {
    try {
        const data = await fetchApi('/api/chartbot/status');

        const activeToggle = document.getElementById('chartbot-active-toggle');
        const activeLabel = document.getElementById('active-status-label');
        activeToggle.checked = data.is_active;
        activeLabel.textContent = data.is_active ? 'Active' : 'Inactive';
        activeLabel.className = data.is_active
            ? 'form-check-label text-success'
            : 'form-check-label text-secondary';

        const nextRunEl = document.getElementById('next-run-time');
        if (data.next_run_time) {
            nextRunEl.textContent = formatDateTime(data.next_run_time);
            nextRunEl.className = 'mb-0 text-primary fw-bold';
        } else {
            nextRunEl.textContent = '예약 없음';
            nextRunEl.className = 'mb-0 text-muted';
        }

        const lastRunEl = document.getElementById('last-run-info');
        if (data.last_run_time && data.last_status) {
            const statusBadge = getStatusBadge(data.last_status);
            lastRunEl.innerHTML = formatDateTime(data.last_run_time) + ' ' + statusBadge;
        } else {
            lastRunEl.textContent = '기록 없음';
        }
    } catch (error) {
        console.error('Failed to load chartbot status:', error);
        showToast('상태 정보를 불러오는데 실패했습니다', 'error');
    }
}

async function loadChartbotSettings() {
    try {
        const data = await fetchApi('/api/chartbot/settings');

        const addTimeInput = document.getElementById('add-notification-time');
        if (addTimeInput) addTimeInput.value = '09:00';

        document.querySelectorAll('.add-day').forEach(function(cb) {
            cb.checked = false;
        });

        const activeToggle = document.getElementById('chartbot-active-toggle');
        activeToggle.checked = data.is_active;
    } catch (error) {
        console.error('Failed to load chartbot settings:', error);
    }
}

async function saveSettings() {
    try {
        const activeToggle = document.getElementById('chartbot-active-toggle');
        const tickers = getTickersFromDOM();

        await fetchApi('/api/chartbot/settings', {
            method: 'POST',
            body: JSON.stringify({
                is_active: activeToggle.checked,
                tickers: tickers,
            }),
        });

        showToast('설정이 저장되었습니다', 'success');
        loadChartbotStatus();
    } catch (error) {
        console.error('Failed to save settings:', error);
        showToast(error.message || '설정 저장에 실패했습니다', 'error');
    }
}

function getTickersFromDOM() {
    const items = document.querySelectorAll('.ticker-item');
    const tickers = [];
    items.forEach(function(item) {
        const ticker = item.dataset.ticker;
        const market = item.dataset.market || 'US';
        const timeInput = item.querySelector('.ticker-notification-time');
        const notificationTime = timeInput ? timeInput.value : '09:00';
        const dayChecks = item.querySelectorAll('.ticker-day-cb:checked');
        const notificationDays = Array.from(dayChecks).map(function(cb) { return parseInt(cb.value, 10); });
        if (ticker) {
            tickers.push({
                ticker: ticker,
                market: market,
                notification_time: notificationTime,
                notification_days: notificationDays,
            });
        }
    });
    return tickers;
}

function getAddNotificationDays() {
    const checked = document.querySelectorAll('.add-day:checked');
    return Array.from(checked).map(function(cb) { return parseInt(cb.value, 10); });
}

async function getCurrentTickers() {
    const data = await fetchApi('/api/chartbot/status');
    return data.tickers || [];
}

async function loadTickers() {
    try {
        const data = await fetchApi('/api/chartbot/status');
        const tickers = data.tickers || [];

        const container = document.getElementById('tickers-container');
        if (tickers.length === 0) {
            container.innerHTML = '<p class="text-muted mb-0">등록된 종목이 없습니다. 위에서 종목을 추가해주세요.</p>';
            return;
        }

        container.innerHTML = tickers.map(function(item) {
            const ticker = item.ticker || item;
            const market = item.market || 'US';
            const name = (item.name && item.name !== ticker) ? item.name : '';
            const notificationTime = item.notification_time || '09:00';
            const notificationDays = Array.isArray(item.notification_days) ? item.notification_days : [0, 1, 2, 3, 4];
            const marketBadge = market === 'US'
                ? '<span class="badge bg-primary">US</span>'
                : '<span class="badge bg-danger">KR</span>';
            const escapedTicker = ticker.replace(/'/g, "\\'");
            const dayCheckboxes = DAY_LABELS.map(function(label, i) {
                const checked = notificationDays.indexOf(i) >= 0 ? ' checked' : '';
                return '<label class="form-check form-check-inline mb-0 small"><input type="checkbox" class="form-check-input ticker-day-cb" value="' + i + '"' + checked + '>' + label + '</label>';
            }).join('');
            var nameHtml = name
                ? '<span class="ticker-name text-muted ms-1" title="' + (name.replace(/"/g, '&quot;')) + '">' + name + '</span>'
                : '';
            return `
                <div class="d-flex align-items-center py-3 border-bottom ticker-item" data-ticker="${ticker}" data-market="${market}">
                    <div class="ticker-info me-4">
                        ${marketBadge} <strong class="flex-shrink-0">${ticker}</strong>${nameHtml}
                    </div>
                    <div class="ticker-days me-4">
                        ${dayCheckboxes}
                    </div>
                    <div class="ticker-time me-4">
                        <input type="time" class="form-control form-control-sm ticker-notification-time" value="${notificationTime}" style="min-width: 160px;" title="발송 시간">
                    </div>
                    <div class="ticker-actions">
                        <button class="btn btn-sm btn-outline-danger" onclick="removeTicker('${escapedTicker}', '${market}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Failed to load tickers:', error);
        document.getElementById('tickers-container').innerHTML =
            '<p class="text-danger mb-0">종목 목록을 불러오는데 실패했습니다</p>';
    }
}

async function addTicker() {
    const tickerInput = document.getElementById('ticker-input');
    const marketSelect = document.getElementById('market-select');
    const timeInput = document.getElementById('add-notification-time');
    const ticker = tickerInput.value.trim().toUpperCase();
    const market = marketSelect.value;
    const notificationTime = timeInput ? timeInput.value : '09:00';
    const notificationDays = getAddNotificationDays();

    if (!ticker) {
        showToast('티커/종목코드를 입력해주세요', 'warning');
        return;
    }

    try {
        await fetchApi('/api/chartbot/tickers', {
            method: 'POST',
            body: JSON.stringify({
                ticker: ticker,
                market: market,
                notification_time: notificationTime,
                notification_days: notificationDays,
            }),
        });

        showToast(`${ticker} 종목이 추가되었습니다`, 'success');
        tickerInput.value = '';
        var nameEl = document.getElementById('add-ticker-name');
        if (nameEl) nameEl.textContent = '';
        loadTickers();
        loadChartbotStatus();
    } catch (error) {
        showToast(error.message || '종목 추가에 실패했습니다', 'error');
    }
}

async function removeTicker(ticker, market) {
    if (!confirm(`"${ticker}" 종목을 제거하시겠습니까?`)) {
        return;
    }

    try {
        await fetchApi(`/api/chartbot/tickers/${encodeURIComponent(ticker)}?market=${market}`, {
            method: 'DELETE',
        });

        showToast('종목이 제거되었습니다', 'success');
        loadTickers();
        loadChartbotStatus();
    } catch (error) {
        showToast(error.message || '종목 제거에 실패했습니다', 'error');
    }
}

async function toggleChartbotActive(checked) {
    try {
        let tickers = getTickersFromDOM();
        if (tickers.length === 0) {
            const data = await fetchApi('/api/chartbot/status');
            tickers = (data.tickers || []).map(function(t) {
                const item = typeof t === 'object' ? t : { ticker: t };
                return {
                    ticker: item.ticker || item,
                    market: item.market || 'US',
                    notification_time: item.notification_time || '09:00',
                    notification_days: Array.isArray(item.notification_days) ? item.notification_days : [0, 1, 2, 3, 4],
                };
            });
        }

        await fetchApi('/api/chartbot/settings', {
            method: 'POST',
            body: JSON.stringify({
                is_active: checked,
                tickers: tickers,
            }),
        });

        showToast(checked ? 'Chartbot이 활성화되었습니다' : 'Chartbot이 비활성화되었습니다', 'success');
        loadChartbotStatus();
    } catch (error) {
        showToast(error.message || '설정 변경에 실패했습니다', 'error');
        document.getElementById('chartbot-active-toggle').checked = !checked;
    }
}

async function testChartbot() {
    const tickerInput = document.getElementById('preview-ticker');
    const marketSelect = document.getElementById('preview-market');
    const ticker = tickerInput ? tickerInput.value.trim().toUpperCase() : '';
    const market = marketSelect ? marketSelect.value : 'US';

    if (!ticker) {
        showToast('티커를 입력해주세요', 'warning');
        return;
    }

    const btn = document.getElementById('test-send-btn');
    const resultEl = document.getElementById('test-result');

    if (btn && btn.disabled) return;

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>발송 중...';
    }
    resultEl.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> 발송 중...';

    try {
        const data = await fetchApi('/api/chartbot/test', {
            method: 'POST',
            body: JSON.stringify({ ticker: ticker, market: market }),
        });

        resultEl.innerHTML = `
            <div class="alert alert-success mb-0">
                <i class="bi bi-check-circle me-1"></i>발송 완료 (${ticker})<br>
                <small>성공: ${data.success}건, 실패: ${data.fail}건</small>
            </div>
        `;
        loadLogs();
        loadChartbotStatus();
    } catch (error) {
        resultEl.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="bi bi-exclamation-triangle me-1"></i>${error.message || '발송 실패'}
            </div>
        `;
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-send me-1"></i>테스트 발송';
        }
    }
}

async function previewChart() {
    const tickerInput = document.getElementById('preview-ticker');
    const ticker = tickerInput.value.trim().toUpperCase();
    const marketSelect = document.getElementById('preview-market');
    const market = marketSelect ? marketSelect.value : 'US';
    const periodSelect = document.getElementById('preview-period');
    const days = periodSelect ? periodSelect.value : '30';
    const periodLabel = periodSelect ? periodSelect.options[periodSelect.selectedIndex].text : '1개월';

    if (!ticker) {
        showToast('티커를 입력해주세요', 'warning');
        return;
    }

    const previewEl = document.getElementById('chart-preview');
    previewEl.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';

    try {
        const data = await fetchApi(`/api/chartbot/preview/${encodeURIComponent(ticker)}?market=${market}&days=${days}`);

        previewEl.innerHTML = `
            <img src="${data.chart_path}" alt="${ticker} chart" class="img-fluid" style="max-height: 300px;">
            <p class="text-muted small mt-2 mb-0">${ticker} (${market}) - 최근 ${periodLabel}</p>
        `;
    } catch (error) {
        previewEl.innerHTML = `
            <div class="text-danger">
                <i class="bi bi-exclamation-triangle me-1"></i>${error.message || '차트 생성 실패'}
            </div>
        `;
    }
}

async function loadLogs() {
    try {
        const data = await fetchApi('/api/chartbot/logs');

        const container = document.getElementById('logs-container');
        if (!data.logs || data.logs.length === 0) {
            container.innerHTML = '<p class="text-muted mb-0">로그가 없습니다</p>';
            return;
        }

        container.innerHTML = data.logs.map(function(log) {
            const statusBadge = getStatusBadge(log.status);
            return `
                <div class="d-flex justify-content-between align-items-start py-2 border-bottom">
                    <div>
                        ${statusBadge}
                        <span class="ms-2">${log.message || '-'}</span>
                    </div>
                    <small class="text-muted">${formatDateTime(log.created_at)}</small>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Failed to load logs:', error);
        document.getElementById('logs-container').innerHTML =
            '<p class="text-danger mb-0">로그를 불러오는데 실패했습니다</p>';
    }
}
