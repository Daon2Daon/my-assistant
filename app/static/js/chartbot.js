// Chartbot JavaScript
// notification_days: 0=월, 1=화, 2=수, 3=목, 4=금, 5=토, 6=일 (Python weekday)
var DAY_LABELS = ['월', '화', '수', '목', '금', '토', '일'];

// 기본 프롬프트 (서버에서 로드 후 저장)
var _defaultPrompt = '';

document.addEventListener('DOMContentLoaded', function() {
    loadChartbotStatus();
    loadChartbotSettings();
    loadTickers();
    loadLogs();
    loadLlmModels();

    const activeToggle = document.getElementById('chartbot-active-toggle');
    activeToggle.addEventListener('change', async function() {
        await toggleChartbotActive(this.checked);
    });

    const aiToggle = document.getElementById('ai-analysis-toggle');
    if (aiToggle) {
        aiToggle.addEventListener('change', function() {
            updateAiAnalysisUiState(this.checked);
        });
    }

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

        // 기본 프롬프트 저장 (복원 버튼용)
        if (data.default_prompt) {
            _defaultPrompt = data.default_prompt;
        }

        // LiteLLM 연결 설정
        const baseUrlInput = document.getElementById('litellm-base-url');
        const apiKeyInput = document.getElementById('litellm-api-key');
        if (baseUrlInput) baseUrlInput.value = data.litellm_base_url || '';
        if (apiKeyInput) apiKeyInput.value = data.litellm_api_key_masked || '';

        // AI 분석 설정 반영
        const ai = data.ai_analysis || {};
        const aiToggle = document.getElementById('ai-analysis-toggle');
        const aiModel = document.getElementById('ai-model-select');
        const aiTemp = document.getElementById('ai-temperature');
        const aiMaxTokens = document.getElementById('ai-max-tokens');
        const aiIncludeWeekly = document.getElementById('ai-include-weekly');
        const aiPrompt = document.getElementById('ai-prompt');

        if (aiToggle) aiToggle.checked = !!ai.enabled;
        if (aiTemp) aiTemp.value = ai.temperature !== undefined ? ai.temperature : 0.4;
        if (aiMaxTokens) aiMaxTokens.value = ai.max_output_tokens || 2000;
        if (aiIncludeWeekly) aiIncludeWeekly.checked = ai.include_weekly !== false;
        if (aiPrompt) aiPrompt.value = ai.prompt || _defaultPrompt;

        // 모델 드롭다운: 서버에서 받은 값이 있으면 선택
        if (aiModel && ai.model) {
            // 옵션에 없으면 추가
            if (!Array.from(aiModel.options).some(o => o.value === ai.model)) {
                const opt = document.createElement('option');
                opt.value = ai.model;
                opt.textContent = ai.model;
                aiModel.appendChild(opt);
            }
            aiModel.value = ai.model;
        }

        updateAiAnalysisUiState(!!ai.enabled);
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

// ── AI 기술분석 관련 함수 ──────────────────────────────────────

function updateAiAnalysisUiState(enabled) {
    const label = document.getElementById('ai-analysis-toggle-label');
    const optionsSection = document.getElementById('ai-analysis-options');
    const promptSection = document.getElementById('ai-prompt-section');

    if (label) {
        label.textContent = enabled ? '활성' : '비활성';
        label.className = enabled ? 'form-check-label text-success fw-bold' : 'form-check-label text-secondary';
    }
    [optionsSection, promptSection].forEach(function(el) {
        if (!el) return;
        if (enabled) {
            el.classList.remove('disabled-section');
        } else {
            el.classList.add('disabled-section');
        }
    });
}

async function loadLlmModels() {
    const modelSelect = document.getElementById('ai-model-select');
    if (!modelSelect) return;

    try {
        const data = await fetchApi('/api/chartbot/llm/models');
        if (!data.models || data.models.length === 0) return;

        // 현재 선택값 보존
        const currentVal = modelSelect.value;
        modelSelect.innerHTML = '';
        data.models.forEach(function(modelId) {
            const opt = document.createElement('option');
            opt.value = modelId;
            opt.textContent = modelId;
            modelSelect.appendChild(opt);
        });

        // 이전 선택값 복원 (있으면)
        if (currentVal && Array.from(modelSelect.options).some(o => o.value === currentVal)) {
            modelSelect.value = currentVal;
        }
    } catch (e) {
        console.warn('LLM 모델 목록 로드 실패:', e);
    }
}

async function saveLitellmSettings() {
    const baseUrlInput = document.getElementById('litellm-base-url');
    const apiKeyInput = document.getElementById('litellm-api-key');

    const payload = {
        litellm_base_url: baseUrlInput ? baseUrlInput.value.trim() : '',
        litellm_api_key: apiKeyInput ? apiKeyInput.value : '',
    };

    try {
        await fetchApi('/api/chartbot/settings', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        showToast('LiteLLM 연결 설정이 저장되었습니다', 'success');
        // 저장 후 마스킹된 값으로 갱신
        await loadChartbotSettings();
        // 모델 목록도 새로 로드 (연결 변경 반영)
        await loadLlmModels();
    } catch (error) {
        showToast(error.message || 'LiteLLM 설정 저장 실패', 'error');
    }
}

async function saveAiAnalysis() {
    const aiToggle = document.getElementById('ai-analysis-toggle');
    const aiModel = document.getElementById('ai-model-select');
    const aiTemp = document.getElementById('ai-temperature');
    const aiMaxTokens = document.getElementById('ai-max-tokens');
    const aiIncludeWeekly = document.getElementById('ai-include-weekly');
    const aiPrompt = document.getElementById('ai-prompt');

    const payload = {
        ai_analysis: {
            enabled: aiToggle ? aiToggle.checked : false,
            model: aiModel ? aiModel.value : 'gemini/gemini-2.5-flash',
            prompt: aiPrompt ? aiPrompt.value : null,
            include_weekly: aiIncludeWeekly ? aiIncludeWeekly.checked : true,
            max_output_tokens: aiMaxTokens ? parseInt(aiMaxTokens.value, 10) : 2000,
            temperature: aiTemp ? parseFloat(aiTemp.value) : 0.4,
        },
    };

    try {
        await fetchApi('/api/chartbot/settings', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        showToast('AI 분석 설정이 저장되었습니다', 'success');
    } catch (error) {
        showToast(error.message || 'AI 분석 설정 저장 실패', 'error');
    }
}

function restoreDefaultPrompt() {
    const aiPrompt = document.getElementById('ai-prompt');
    if (!aiPrompt) return;
    if (!_defaultPrompt) {
        showToast('기본 프롬프트를 불러오는 중입니다. 잠시 후 다시 시도해주세요.', 'warning');
        return;
    }
    if (!confirm('현재 프롬프트를 기본값으로 되돌리시겠습니까?')) return;
    aiPrompt.value = _defaultPrompt;
    showToast('기본 프롬프트로 복원되었습니다', 'success');
}

// ── 통합 테스트 패널 (차트 생성 → AI 분석 → 텔레그램 발송) ────

// 마지막 생성한 차트 컨텍스트 (AI 분석 재사용용)
var _lastChartContext = null;  // {ticker, market, name, charts: [{path, url, label}, ...]}

function _getTestInputs() {
    const tickerInput = document.getElementById('test-ticker');
    const marketSelect = document.getElementById('test-market');
    return {
        ticker: tickerInput ? tickerInput.value.trim().toUpperCase() : '',
        market: marketSelect ? marketSelect.value : 'US',
    };
}

function _renderChartsHtml(name, ticker, charts) {
    let html = '<div class="mb-2 text-muted small">' +
        '<i class="bi bi-person-circle me-1"></i>' + (name || ticker) + ' (' + ticker + ')</div>';
    (charts || []).forEach(function(c) {
        html += '<div class="text-center mb-3">' +
            '<img src="' + c.url + '" alt="' + c.label + '" class="img-fluid" style="max-height: 380px;">' +
            '<p class="text-muted small mt-1 mb-0">' + c.label + '</p>' +
            '</div>';
    });
    return html;
}

function _setTestBtnState(btnId, busy, originalHtml) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    if (busy) {
        btn.dataset.origHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>처리 중...';
    } else {
        btn.disabled = false;
        btn.innerHTML = originalHtml || btn.dataset.origHtml || btn.innerHTML;
    }
}

function _setTestResult(html) {
    const resultEl = document.getElementById('test-result');
    if (resultEl) resultEl.innerHTML = html;
}

async function runTestChart() {
    const { ticker, market } = _getTestInputs();
    if (!ticker) { showToast('티커를 입력해주세요', 'warning'); return; }

    _setTestBtnState('btn-test-chart', true);
    _setTestResult('<div class="text-muted"><span class="spinner-border spinner-border-sm me-2"></span>일봉+주봉 차트 생성 중...</div>');

    try {
        const data = await fetchApi('/api/chartbot/test-charts', {
            method: 'POST',
            body: JSON.stringify({ ticker: ticker, market: market }),
        });

        const charts = data.charts || [];
        _setTestResult(_renderChartsHtml(data.name, data.ticker, charts));

        // 컨텍스트 캐시 (AI 분석에서 재사용)
        _lastChartContext = {
            ticker: ticker,
            market: market,
            name: data.name,
            charts: charts,
        };
    } catch (error) {
        _setTestResult(
            '<div class="text-danger"><i class="bi bi-exclamation-triangle me-1"></i>' +
            (error.message || '차트 생성 실패') + '</div>'
        );
    } finally {
        _setTestBtnState('btn-test-chart', false, '<i class="bi bi-bar-chart me-1"></i>1) 차트 생성');
    }
}

async function runTestAi() {
    const { ticker, market } = _getTestInputs();
    if (!ticker) { showToast('티커를 입력해주세요', 'warning'); return; }

    _setTestBtnState('btn-test-ai', true);

    // 캐시 유효성 검사 (같은 ticker+market의 차트가 있을 때 재사용)
    const cacheValid = _lastChartContext
        && _lastChartContext.ticker === ticker
        && _lastChartContext.market === market
        && _lastChartContext.charts
        && _lastChartContext.charts.length > 0;

    // 로딩 표시 (캐시가 있으면 차트는 유지하고 그 아래에 로딩, 없으면 전체 영역에 로딩)
    const loadingMsg = cacheValid
        ? '기존 차트로 AI 분석 중... (10~30초)'
        : '차트 생성 + AI 분석 중... (10~30초)';
    const loadingHtml = '<div class="text-muted"><span class="spinner-border spinner-border-sm me-2"></span>' + loadingMsg + '</div>';

    if (cacheValid) {
        _setTestResult(
            _renderChartsHtml(_lastChartContext.name, ticker, _lastChartContext.charts) +
            '<hr class="my-3">' + loadingHtml
        );
    } else {
        _setTestResult(loadingHtml);
    }

    // 페이로드 구성 (캐시가 있으면 경로 전달)
    const payload = { ticker: ticker, market: market };
    if (cacheValid) {
        const daily = _lastChartContext.charts[0];
        const weekly = _lastChartContext.charts[1];
        if (daily) payload.daily_path = daily.path;
        if (weekly) payload.weekly_path = weekly.path;
    }

    try {
        const data = await fetchApi('/api/chartbot/analyze-preview', {
            method: 'POST',
            body: JSON.stringify(payload),
        });

        // 차트 (서버가 항상 반환) + AI 분석 결과
        const chartsHtml = _renderChartsHtml(data.name, data.ticker, data.charts || []);
        const aiHtml =
            '<hr class="my-3">' +
            '<div class="mb-2 text-muted small">' +
            '<i class="bi bi-robot me-1"></i>AI 분석 결과 · ' +
            '<i class="bi bi-clock me-1"></i>' + data.elapsed_sec + '초' +
            (data.cached_charts_used ? ' · <i class="bi bi-recycle me-1"></i>기존 차트 재사용' : '') +
            '</div>' +
            '<div style="white-space: pre-wrap; font-size: 0.88rem;">' +
            (data.analysis_html || '') + '</div>';

        _setTestResult(chartsHtml + aiHtml);

        // 캐시 갱신 (서버가 새 차트 생성했을 수 있음)
        _lastChartContext = {
            ticker: ticker,
            market: market,
            name: data.name,
            charts: data.charts || [],
        };
    } catch (error) {
        const errHtml = '<div class="text-danger mt-2"><i class="bi bi-exclamation-triangle me-1"></i>' +
            (error.message || 'AI 분석 실패 (AI 기술분석이 활성화되어 있는지 확인하세요)') + '</div>';
        if (cacheValid) {
            // 차트는 유지하고 에러만 표시
            _setTestResult(
                _renderChartsHtml(_lastChartContext.name, ticker, _lastChartContext.charts) +
                '<hr class="my-3">' + errHtml
            );
        } else {
            _setTestResult(errHtml);
        }
    } finally {
        _setTestBtnState('btn-test-ai', false, '<i class="bi bi-robot me-1"></i>2) AI 분석');
    }
}

async function runTestSend() {
    const { ticker, market } = _getTestInputs();
    if (!ticker) { showToast('티커를 입력해주세요', 'warning'); return; }

    _setTestBtnState('btn-test-send', true);
    _setTestResult('<div class="text-muted"><span class="spinner-border spinner-border-sm me-2"></span>텔레그램 발송 중...</div>');

    try {
        const data = await fetchApi('/api/chartbot/test', {
            method: 'POST',
            body: JSON.stringify({ ticker: ticker, market: market }),
        });
        _setTestResult(
            '<div class="alert alert-success mb-0">' +
            '<i class="bi bi-check-circle me-1"></i>발송 완료 (' + ticker + ')<br>' +
            '<small>성공: ' + data.success + '건 · 실패: ' + data.fail + '건</small>' +
            '</div>'
        );
        loadLogs();
        loadChartbotStatus();
    } catch (error) {
        _setTestResult(
            '<div class="alert alert-danger mb-0"><i class="bi bi-exclamation-triangle me-1"></i>' +
            (error.message || '발송 실패') + '</div>'
        );
    } finally {
        _setTestBtnState('btn-test-send', false, '<i class="bi bi-send me-1"></i>텔레그램 발송');
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
