// Finance JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadFinanceStatus();
    loadFinanceSettings();
    loadUSWatchlist();
    loadKRWatchlist();
    loadLogs();
    loadPriceAlerts();
    loadWatchlistSelectOptions();

    // 활성화 토글 이벤트 리스너
    const activeToggle = document.getElementById('finance-active-toggle');
    activeToggle.addEventListener('change', async function() {
        await toggleFinanceActive(this.checked);
    });

    // 알림 유형 변경 이벤트 리스너
    const alertTypeSelect = document.getElementById('alert-type-select');
    alertTypeSelect.addEventListener('change', updateAlertValueHint);
});

// 금융 모듈 상태 로드
async function loadFinanceStatus() {
    try {
        const data = await fetchApi('/api/finance/status');

        // 활성화 상태
        const activeToggle = document.getElementById('finance-active-toggle');
        const activeLabel = document.getElementById('active-status-label');
        activeToggle.checked = data.is_active;
        activeLabel.textContent = data.is_active ? 'Active' : 'Inactive';
        activeLabel.className = data.is_active ? 'form-check-label text-success' : 'form-check-label text-secondary';

        // US 다음 발송 예정 시간
        const usNextRunEl = document.getElementById('us-next-run-time');
        if (data.us_next_run_time) {
            usNextRunEl.textContent = formatDateTime(data.us_next_run_time);
            usNextRunEl.className = 'mb-0 text-primary fw-bold';
        } else {
            usNextRunEl.textContent = '예약 없음';
            usNextRunEl.className = 'mb-0 text-muted';
        }

        // KR 다음 발송 예정 시간
        const krNextRunEl = document.getElementById('kr-next-run-time');
        if (data.kr_next_run_time) {
            krNextRunEl.textContent = formatDateTime(data.kr_next_run_time);
            krNextRunEl.className = 'mb-0 text-danger fw-bold';
        } else {
            krNextRunEl.textContent = '예약 없음';
            krNextRunEl.className = 'mb-0 text-muted';
        }

        // 마지막 발송 결과
        const lastRunEl = document.getElementById('last-run-info');
        if (data.last_run_time && data.last_status) {
            const statusBadge = {
                'SUCCESS': '<span class="badge bg-success">SUCCESS</span>',
                'FAIL': '<span class="badge bg-danger">FAIL</span>',
                'SKIP': '<span class="badge bg-warning">SKIP</span>'
            }[data.last_status] || `<span class="badge bg-secondary">${data.last_status}</span>`;

            lastRunEl.innerHTML = `${formatDateTime(data.last_run_time)} ${statusBadge}`;
        } else {
            lastRunEl.textContent = '기록 없음';
        }

    } catch (error) {
        console.error('Failed to load finance status:', error);
        showToast('상태 정보를 불러오는데 실패했습니다', 'error');
    }
}

// 금융 설정 로드
async function loadFinanceSettings() {
    try {
        const data = await fetchApi('/api/settings/finance');

        // config_json에서 시간 설정 불러오기
        let usTime = '22:00';
        let krTime = '09:00';

        if (data.config_json) {
            try {
                const config = JSON.parse(data.config_json);
                usTime = config.us_notification_time || data.notification_time || '22:00';
                krTime = config.kr_notification_time || '09:00';
            } catch (e) {
                console.warn('설정 파싱 실패, 기본값 사용:', e);
                usTime = data.notification_time || '22:00';
            }
        } else {
            usTime = data.notification_time || '22:00';
        }

        // 알림 시간 설정
        const timeInput = document.getElementById('us-notification-time');
        timeInput.value = usTime;

        const krTimeInput = document.getElementById('kr-notification-time');
        krTimeInput.value = krTime;

    } catch (error) {
        console.error('Failed to load finance settings:', error);
    }
}

// 활성화 토글
async function toggleFinanceActive(isActive) {
    try {
        await fetchApi('/api/settings/finance', {
            method: 'PUT',
            body: JSON.stringify({ is_active: isActive })
        });

        const activeLabel = document.getElementById('active-status-label');
        activeLabel.textContent = isActive ? 'Active' : 'Inactive';
        activeLabel.className = isActive ? 'form-check-label text-success' : 'form-check-label text-secondary';

        showToast(`금융 알림 ${isActive ? '활성화' : '비활성화'}`, 'success');

        // 상태 새로고침
        setTimeout(() => loadFinanceStatus(), 1000);

    } catch (error) {
        // 토글 상태 되돌리기
        const activeToggle = document.getElementById('finance-active-toggle');
        activeToggle.checked = !isActive;
        showToast('설정 변경에 실패했습니다', 'error');
    }
}

// 설정 저장
async function saveSettings() {
    try {
        const usNotificationTime = document.getElementById('us-notification-time').value;
        const krNotificationTime = document.getElementById('kr-notification-time').value;

        if (!usNotificationTime) {
            showToast('US Market 알림 시간을 선택해주세요', 'warning');
            return;
        }

        if (!krNotificationTime) {
            showToast('KR Market 알림 시간을 선택해주세요', 'warning');
            return;
        }

        // US와 KR 시간을 config_json에 저장
        const config = {
            us_notification_time: usNotificationTime,
            kr_notification_time: krNotificationTime
        };

        await fetchApi('/api/settings/finance', {
            method: 'PUT',
            body: JSON.stringify({
                notification_time: usNotificationTime, // 기본값으로 US 시간 사용
                config_json: JSON.stringify(config)
            })
        });

        showToast('설정이 저장되었습니다', 'success');

        // 상태 새로고침
        setTimeout(() => loadFinanceStatus(), 1000);

    } catch (error) {
        showToast('설정 저장에 실패했습니다', 'error');
    }
}

// US Market 미리보기
async function loadUSPreview() {
    const previewContainer = document.getElementById('us-preview');

    previewContainer.innerHTML = `
        <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">불러오는 중...</span>
        </div>
    `;

    try {
        const data = await fetchApi('/api/finance/preview/us');

        previewContainer.innerHTML = `
            <div class="alert alert-info mb-0">
                <small class="text-muted d-block mb-2">미리보기 (US Market)</small>
                <pre class="mb-0" style="white-space: pre-wrap; font-size: 0.9rem;">${data.message}</pre>
            </div>
        `;

    } catch (error) {
        previewContainer.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="bi bi-exclamation-triangle me-2"></i>
                미리보기를 불러오는데 실패했습니다
            </div>
        `;
    }
}

// KR Market 미리보기
async function loadKRPreview() {
    const previewContainer = document.getElementById('kr-preview');

    previewContainer.innerHTML = `
        <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">불러오는 중...</span>
        </div>
    `;

    try {
        const data = await fetchApi('/api/finance/preview/kr');

        previewContainer.innerHTML = `
            <div class="alert alert-info mb-0">
                <small class="text-muted d-block mb-2">미리보기 (KR Market)</small>
                <pre class="mb-0" style="white-space: pre-wrap; font-size: 0.9rem;">${data.message}</pre>
            </div>
        `;

    } catch (error) {
        previewContainer.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="bi bi-exclamation-triangle me-2"></i>
                미리보기를 불러오는데 실패했습니다
            </div>
        `;
    }
}

// US Market 테스트 발송
async function testUSMarket() {
    const resultEl = document.getElementById('us-test-result');

    resultEl.innerHTML = `
        <div class="alert alert-info mb-0">
            <i class="bi bi-hourglass-split me-2"></i>테스트 발송 중...
        </div>
    `;

    try {
        const data = await fetchApi('/api/finance/test/us', { method: 'POST' });

        resultEl.innerHTML = `
            <div class="alert alert-success mb-0">
                <i class="bi bi-check-circle me-2"></i>${data.message}
            </div>
        `;

        // 로그 새로고침
        setTimeout(() => {
            loadLogs();
            loadFinanceStatus();
        }, 2000);

    } catch (error) {
        resultEl.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="bi bi-x-circle me-2"></i>테스트 발송 실패: ${error.message}
            </div>
        `;
    }
}

// KR Market 테스트 발송
async function testKRMarket() {
    const resultEl = document.getElementById('kr-test-result');

    resultEl.innerHTML = `
        <div class="alert alert-info mb-0">
            <i class="bi bi-hourglass-split me-2"></i>테스트 발송 중...
        </div>
    `;

    try {
        const data = await fetchApi('/api/finance/test/kr', { method: 'POST' });

        resultEl.innerHTML = `
            <div class="alert alert-success mb-0">
                <i class="bi bi-check-circle me-2"></i>${data.message}
            </div>
        `;

        // 로그 새로고침
        setTimeout(() => {
            loadLogs();
            loadFinanceStatus();
        }, 2000);

    } catch (error) {
        resultEl.innerHTML = `
            <div class="alert alert-danger mb-0">
                <i class="bi bi-x-circle me-2"></i>테스트 발송 실패: ${error.message}
            </div>
        `;
    }
}

// 로그 로드
async function loadLogs() {
    const container = document.getElementById('logs-container');

    try {
        const data = await fetchApi('/api/finance/logs?limit=20');

        if (data.logs.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">로그가 없습니다</p>';
            return;
        }

        let html = '';
        data.logs.forEach(log => {
            const statusClass = {
                'SUCCESS': 'border-success',
                'FAIL': 'border-danger',
                'SKIP': 'border-warning'
            }[log.status] || 'border-secondary';

            const statusBadge = {
                'SUCCESS': '<span class="badge bg-success">SUCCESS</span>',
                'FAIL': '<span class="badge bg-danger">FAIL</span>',
                'SKIP': '<span class="badge bg-warning">SKIP</span>'
            }[log.status] || `<span class="badge bg-secondary">${log.status}</span>`;

            html += `
                <div class="border-start border-3 ${statusClass} ps-3 pb-3 mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        ${statusBadge}
                        <small class="text-muted">${formatDateTime(log.created_at)}</small>
                    </div>
                    <div class="text-muted small">${log.message}</div>
                </div>
            `;
        });

        container.innerHTML = html;

    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">로그를 불러오는데 실패했습니다</p>';
    }
}

// ============================================================
// 관심 종목 관리 기능
// ============================================================

// US Market 관심 종목 목록 로드
async function loadUSWatchlist() {
    const container = document.getElementById('us-watchlist-container');

    container.innerHTML = `
        <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">Loading...</span>
        </div>
    `;

    try {
        const data = await fetchApi('/api/finance/watchlist');
        const usStocks = data.watchlists.filter(stock => stock.market === 'US');

        if (usStocks.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">등록된 종목이 없습니다</p>';
            return;
        }

        let html = '<div class="row" id="us-sortable-list">';
        for (const stock of usStocks) {
            html += renderWatchlistCard(stock);
        }
        html += '</div>';

        container.innerHTML = html;

        // SortableJS 초기화
        initializeSortable('us-sortable-list', 'US');

    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">종목 목록을 불러오는데 실패했습니다</p>';
    }
}

// KR Market 관심 종목 목록 로드
async function loadKRWatchlist() {
    const container = document.getElementById('kr-watchlist-container');

    container.innerHTML = `
        <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">Loading...</span>
        </div>
    `;

    try {
        const data = await fetchApi('/api/finance/watchlist');
        const krStocks = data.watchlists.filter(stock => stock.market === 'KR');

        if (krStocks.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">등록된 종목이 없습니다</p>';
            return;
        }

        let html = '<div class="row" id="kr-sortable-list">';
        for (const stock of krStocks) {
            html += renderWatchlistCard(stock);
        }
        html += '</div>';

        container.innerHTML = html;

        // SortableJS 초기화
        initializeSortable('kr-sortable-list', 'KR');

    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">종목 목록을 불러오는데 실패했습니다</p>';
    }
}

// 관심 종목 카드 렌더링
function renderWatchlistCard(stock) {
    const marketBadge = stock.market === 'US'
        ? '<span class="badge bg-primary">US</span>'
        : '<span class="badge bg-danger">KR</span>';

    return `
        <div class="col-md-6 col-lg-4 mb-3 watchlist-item" data-id="${stock.watchlist_id}">
            <div class="card h-100">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <div class="d-flex align-items-center">
                            <i class="bi bi-grip-vertical text-muted me-2 drag-handle" style="cursor: grab;"></i>
                            <div>
                                <h6 class="mb-0">${stock.ticker}</h6>
                                <small class="text-muted">${stock.name || stock.ticker}</small>
                            </div>
                        </div>
                        ${marketBadge}
                    </div>
                    <div class="mt-3">
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteWatchlist(${stock.watchlist_id})">
                            <i class="bi bi-trash me-1"></i>삭제
                        </button>
                        <button class="btn btn-sm btn-outline-info" onclick="viewStockDetail('${stock.ticker}', '${stock.market}')">
                            <i class="bi bi-info-circle me-1"></i>시세
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// 관심 종목 등록
async function addWatchlist(market) {
    const inputId = market === 'US' ? 'us-ticker-input' : 'kr-ticker-input';
    const ticker = document.getElementById(inputId).value.trim().toUpperCase();

    if (!ticker) {
        showToast('티커를 입력해주세요', 'warning');
        return;
    }

    try {
        const payload = {
            ticker: ticker,
            market: market
        };

        await fetchApi('/api/finance/watchlist', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        showToast('종목이 등록되었습니다', 'success');

        // 입력 필드 초기화
        document.getElementById(inputId).value = '';

        // 해당 시장 목록 새로고침
        if (market === 'US') {
            loadUSWatchlist();
        } else {
            loadKRWatchlist();
        }

    } catch (error) {
        showToast(`등록 실패: ${error.message}`, 'error');
    }
}

// 관심 종목 삭제
async function deleteWatchlist(watchlistId) {
    if (!confirm('이 종목을 삭제하시겠습니까?')) {
        return;
    }

    try {
        await fetchApi(`/api/finance/watchlist/${watchlistId}`, {
            method: 'DELETE'
        });

        showToast('종목이 삭제되었습니다', 'success');

        // 양쪽 목록 모두 새로고침
        loadUSWatchlist();
        loadKRWatchlist();

    } catch (error) {
        showToast(`삭제 실패: ${error.message}`, 'error');
    }
}

// 종목 상세 정보 보기
async function viewStockDetail(ticker, market) {
    const modalHtml = `
        <div class="modal fade" id="stockDetailModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${ticker} 상세 정보</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" id="stock-detail-body">
                        <div class="text-center py-4">
                            <div class="spinner-border" role="status"></div>
                            <p class="mt-2">종목 정보를 불러오는 중...</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 기존 모달 제거
    const existingModal = document.getElementById('stockDetailModal');
    if (existingModal) {
        existingModal.remove();
    }

    // 새 모달 추가
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = new bootstrap.Modal(document.getElementById('stockDetailModal'));
    modal.show();

    // 데이터 로드
    try {
        const data = await fetchApi(`/api/finance/quote/${ticker}?market=${market}`);

        const quote = data.quote;
        const periodChanges = data.period_changes;
        const week52 = data.week_52_range;

        const changeEmoji = quote.change_percent >= 0 ? '🔺' : '🔻';
        const changeSign = quote.change_percent >= 0 ? '+' : '';
        const priceFormat = market === 'US' ? `$${quote.price.toFixed(2)}` : `${quote.price.toLocaleString()}원`;

        let detailHtml = `
            <div class="mb-4">
                <h4>${quote.name}</h4>
                <h3 class="mb-0">${changeEmoji} ${priceFormat}</h3>
                <p class="text-muted">${changeSign}${quote.change_percent.toFixed(2)}%</p>
            </div>
        `;

        if (periodChanges) {
            detailHtml += `
                <div class="mb-4">
                    <h6>기간별 변동률</h6>
                    <div class="row">
                        <div class="col-4">
                            <div class="text-center p-2 border rounded">
                                <small class="text-muted d-block">일간</small>
                                <strong class="${periodChanges.daily >= 0 ? 'text-success' : 'text-danger'}">
                                    ${periodChanges.daily >= 0 ? '+' : ''}${periodChanges.daily.toFixed(2)}%
                                </strong>
                            </div>
                        </div>
                        <div class="col-4">
                            <div class="text-center p-2 border rounded">
                                <small class="text-muted d-block">주간</small>
                                <strong class="${periodChanges.weekly >= 0 ? 'text-success' : 'text-danger'}">
                                    ${periodChanges.weekly >= 0 ? '+' : ''}${periodChanges.weekly.toFixed(2)}%
                                </strong>
                            </div>
                        </div>
                        <div class="col-4">
                            <div class="text-center p-2 border rounded">
                                <small class="text-muted d-block">월간</small>
                                <strong class="${periodChanges.monthly >= 0 ? 'text-success' : 'text-danger'}">
                                    ${periodChanges.monthly >= 0 ? '+' : ''}${periodChanges.monthly.toFixed(2)}%
                                </strong>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        if (week52) {
            const lowFormat = market === 'US' ? week52.low.toFixed(2) : week52.low.toLocaleString();
            const highFormat = market === 'US' ? week52.high.toFixed(2) : week52.high.toLocaleString();

            detailHtml += `
                <div class="mb-3">
                    <h6>52주 범위</h6>
                    <div class="d-flex justify-content-between mb-2">
                        <small>최저: ${lowFormat}</small>
                        <small>최고: ${highFormat}</small>
                    </div>
                    <div class="progress" style="height: 20px;">
                        <div class="progress-bar" role="progressbar"
                             style="width: ${week52.position_percent}%"
                             aria-valuenow="${week52.position_percent}" aria-valuemin="0" aria-valuemax="100">
                            ${week52.position_percent.toFixed(1)}%
                        </div>
                    </div>
                </div>
            `;
        }

        detailHtml += `
            <div class="text-muted small">
                <i class="bi bi-info-circle me-1"></i>
                조회 시간: ${new Date(data.timestamp).toLocaleString('ko-KR')}
            </div>
        `;

        document.getElementById('stock-detail-body').innerHTML = detailHtml;

    } catch (error) {
        document.getElementById('stock-detail-body').innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle me-2"></i>
                종목 정보를 불러오는데 실패했습니다: ${error.message}
            </div>
        `;
    }
}

// ========================================
// 가격 알림 관리 함수
// ========================================

/**
 * 가격 알림 목록 로드
 */
async function loadPriceAlerts() {
    const container = document.getElementById('alerts-container');

    try {
        const data = await fetchApi('/api/finance/alerts');

        if (!data.alerts || data.alerts.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-3">
                    <i class="bi bi-bell-slash me-2"></i>
                    등록된 가격 알림이 없습니다
                </div>
            `;
            return;
        }

        let html = '<div class="row">';

        data.alerts.forEach(alert => {
            const isTriggered = alert.is_triggered;
            const badgeClass = isTriggered ? 'bg-secondary' : 'bg-success';
            const statusText = isTriggered ? '발동됨' : '활성';

            let alertTypeText = '';
            let targetValue = '';

            if (alert.alert_type === 'TARGET_HIGH') {
                alertTypeText = '목표가 (상승)';
                targetValue = `$${alert.target_price.toFixed(2)}`;
            } else if (alert.alert_type === 'TARGET_LOW') {
                alertTypeText = '손절가 (하락)';
                targetValue = `$${alert.target_price.toFixed(2)}`;
            } else if (alert.alert_type === 'PERCENT_CHANGE') {
                alertTypeText = '일일 변동률';
                targetValue = `${alert.target_percent > 0 ? '+' : ''}${alert.target_percent}%`;
            }

            html += `
                <div class="col-md-6 mb-3">
                    <div class="card ${isTriggered ? 'border-secondary' : 'border-success'}">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div>
                                    <h6 class="mb-1">
                                        <span class="badge ${alert.market === 'US' ? 'bg-primary' : 'bg-danger'}">${alert.market}</span>
                                        ${alert.ticker}
                                    </h6>
                                </div>
                                <span class="badge ${badgeClass}">${statusText}</span>
                            </div>
                            <p class="mb-1 small">
                                <strong>알림 유형:</strong> ${alertTypeText}
                            </p>
                            <p class="mb-1 small">
                                <strong>목표 값:</strong> ${targetValue}
                            </p>
                            <p class="mb-2 small text-muted">
                                등록: ${formatDateTime(alert.created_at)}
                            </p>
                            ${isTriggered ? `
                                <p class="mb-2 small text-success">
                                    <i class="bi bi-check-circle me-1"></i>
                                    발동: ${formatDateTime(alert.triggered_at)}
                                </p>
                            ` : ''}
                            <button class="btn btn-sm btn-outline-danger" onclick="deletePriceAlert(${alert.alert_id})">
                                <i class="bi bi-trash me-1"></i>삭제
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;

    } catch (error) {
        container.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle me-2"></i>
                가격 알림 목록을 불러오는데 실패했습니다: ${error.message}
            </div>
        `;
    }
}

/**
 * 관심 종목 목록을 select box에 로드
 */
async function loadWatchlistSelectOptions() {
    const select = document.getElementById('alert-watchlist-select');

    try {
        const data = await fetchApi('/api/finance/watchlist');

        // 기본 옵션
        let html = '<option value="">종목을 선택하세요</option>';

        if (data.watchlists && data.watchlists.length > 0) {
            data.watchlists.forEach(stock => {
                const displayName = stock.name ? `${stock.ticker} (${stock.name})` : stock.ticker;
                html += `<option value="${stock.watchlist_id}" data-ticker="${stock.ticker}" data-market="${stock.market}">${displayName} [${stock.market}]</option>`;
            });
        }

        select.innerHTML = html;

    } catch (error) {
        console.error('관심 종목 목록 로드 실패:', error);
        showToast('관심 종목 목록을 불러오는데 실패했습니다', 'error');
    }
}

/**
 * 알림 유형 변경 시 입력 힌트 업데이트
 */
function updateAlertValueHint() {
    const alertType = document.getElementById('alert-type-select').value;
    const hint = document.getElementById('alert-value-hint');
    const input = document.getElementById('alert-value-input');

    if (alertType === 'TARGET_HIGH' || alertType === 'TARGET_LOW') {
        hint.textContent = '목표 가격 (USD)';
        input.placeholder = '예: 150.00';
    } else if (alertType === 'PERCENT_CHANGE') {
        hint.textContent = '목표 변동률 (%)';
        input.placeholder = '예: 5.0 또는 -3.0';
    }
}

/**
 * 가격 알림 등록
 */
async function createPriceAlert() {
    const watchlistId = document.getElementById('alert-watchlist-select').value;
    const alertType = document.getElementById('alert-type-select').value;
    const alertValue = parseFloat(document.getElementById('alert-value-input').value);

    // 유효성 검사
    if (!watchlistId) {
        showToast('종목을 선택해주세요', 'warning');
        return;
    }

    if (!alertValue || isNaN(alertValue)) {
        showToast('목표 값을 입력해주세요', 'warning');
        return;
    }

    if ((alertType === 'TARGET_HIGH' || alertType === 'TARGET_LOW') && alertValue <= 0) {
        showToast('목표가는 0보다 커야 합니다', 'warning');
        return;
    }

    try {
        const payload = {
            watchlist_id: parseInt(watchlistId),
            alert_type: alertType
        };

        // 알림 유형에 따라 target_price 또는 target_percent 설정
        if (alertType === 'TARGET_HIGH' || alertType === 'TARGET_LOW') {
            payload.target_price = alertValue;
        } else if (alertType === 'PERCENT_CHANGE') {
            payload.target_percent = alertValue;
        }

        await fetchApi('/api/finance/alerts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        // 알림 목록 새로고침 (먼저 실행)
        await loadPriceAlerts();

        // 입력 필드 초기화
        document.getElementById('alert-watchlist-select').value = '';
        document.getElementById('alert-value-input').value = '';

        showToast('가격 알림이 등록되었습니다', 'success');

    } catch (error) {
        showToast(`가격 알림 등록 실패: ${error.message}`, 'error');
    }
}

/**
 * 가격 알림 삭제
 */
async function deletePriceAlert(alertId) {
    if (!confirm('이 가격 알림을 삭제하시겠습니까?')) {
        return;
    }

    try {
        await fetchApi(`/api/finance/alerts/${alertId}`, {
            method: 'DELETE'
        });

        // 알림 목록 새로고침 (먼저 실행)
        await loadPriceAlerts();

        showToast('가격 알림이 삭제되었습니다', 'success');

    } catch (error) {
        showToast(`가격 알림 삭제 실패: ${error.message}`, 'error');
    }
}

// ========================================
// Drag & Drop 순서 변경 기능
// ========================================

/**
 * SortableJS 초기화
 */
function initializeSortable(listId, market) {
    const listElement = document.getElementById(listId);

    if (!listElement) {
        return;
    }

    new Sortable(listElement, {
        animation: 150,
        handle: '.drag-handle',
        ghostClass: 'sortable-ghost',
        chosenClass: 'sortable-chosen',
        dragClass: 'sortable-drag',
        onEnd: function(evt) {
            // 드래그 종료 시 순서 저장
            saveWatchlistOrder(listId, market);
        }
    });
}

/**
 * 관심 종목 순서 저장
 */
async function saveWatchlistOrder(listId, market) {
    const listElement = document.getElementById(listId);
    const items = listElement.querySelectorAll('.watchlist-item');

    // 순서 데이터 생성
    const orders = [];
    items.forEach((item, index) => {
        const watchlistId = parseInt(item.getAttribute('data-id'));
        orders.push({
            watchlist_id: watchlistId,
            display_order: index
        });
    });

    const requestData = { orders: orders };
    console.log('순서 저장 요청:', requestData);

    try {
        const response = await fetchApi('/api/finance/watchlists/reorder', {
            method: 'PUT',
            body: JSON.stringify(requestData)
        });

        console.log('순서 저장 응답:', response);
        showToast('순서가 저장되었습니다', 'success');

    } catch (error) {
        console.error('순서 저장 실패:', error);
        const errorMsg = error.message || error.toString() || '알 수 없는 오류';
        showToast(`순서 저장 실패: ${errorMsg}`, 'error');

        // 실패 시 목록 다시 로드
        if (market === 'US') {
            loadUSWatchlist();
        } else {
            loadKRWatchlist();
        }
    }
}
