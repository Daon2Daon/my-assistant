// Weather JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadWeatherStatus();
    loadWeatherSettings();
    loadLogs();

    // 활성화 토글 이벤트 리스너
    const activeToggle = document.getElementById('weather-active-toggle');
    activeToggle.addEventListener('change', async function() {
        await toggleWeatherActive(this.checked);
    });
});

// 날씨 모듈 상태 로드
async function loadWeatherStatus() {
    try {
        const data = await fetchApi('/api/weather/status');

        // 활성화 상태
        const activeToggle = document.getElementById('weather-active-toggle');
        const activeLabel = document.getElementById('active-status-label');
        activeToggle.checked = data.is_active;
        activeLabel.textContent = data.is_active ? 'Active' : 'Inactive';
        activeLabel.className = data.is_active ? 'form-check-label text-success' : 'form-check-label text-secondary';

        // 다음 발송 예정 시간
        const nextRunEl = document.getElementById('next-run-time');
        if (data.next_run_time) {
            nextRunEl.textContent = formatDateTime(data.next_run_time);
            nextRunEl.className = 'mb-0 text-primary fw-bold';
        } else {
            nextRunEl.textContent = '예약 없음';
            nextRunEl.className = 'mb-0 text-muted';
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
        console.error('Failed to load weather status:', error);
        showToast('상태 정보를 불러오는데 실패했습니다', 'error');
    }
}

// 날씨 설정 로드
async function loadWeatherSettings() {
    try {
        const data = await fetchApi('/api/settings/weather');

        // 알림 시간 설정
        const timeInput = document.getElementById('notification-time');
        timeInput.value = data.notification_time || '07:00';

    } catch (error) {
        console.error('Failed to load weather settings:', error);
    }
}

// 활성화 토글
async function toggleWeatherActive(isActive) {
    try {
        await fetchApi('/api/settings/weather', {
            method: 'PUT',
            body: JSON.stringify({ is_active: isActive })
        });

        const activeLabel = document.getElementById('active-status-label');
        activeLabel.textContent = isActive ? 'Active' : 'Inactive';
        activeLabel.className = isActive ? 'form-check-label text-success' : 'form-check-label text-secondary';

        showToast(`날씨 알림 ${isActive ? '활성화' : '비활성화'}`, 'success');

        // 상태 새로고침
        setTimeout(() => loadWeatherStatus(), 1000);

    } catch (error) {
        // 토글 상태 되돌리기
        const activeToggle = document.getElementById('weather-active-toggle');
        activeToggle.checked = !isActive;
        showToast('설정 변경에 실패했습니다', 'error');
    }
}

// 설정 저장
async function saveSettings() {
    try {
        const notificationTime = document.getElementById('notification-time').value;

        if (!notificationTime) {
            showToast('알림 시간을 선택해주세요', 'warning');
            return;
        }

        await fetchApi('/api/settings/weather', {
            method: 'PUT',
            body: JSON.stringify({
                notification_time: notificationTime
            })
        });

        showToast('설정이 저장되었습니다', 'success');

        // 상태 새로고침
        setTimeout(() => loadWeatherStatus(), 1000);

    } catch (error) {
        showToast('설정 저장에 실패했습니다', 'error');
    }
}

// 메시지 미리보기
async function loadPreview() {
    const previewContainer = document.getElementById('message-preview');
    const city = document.getElementById('city-select').value;

    previewContainer.innerHTML = `
        <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">불러오는 중...</span>
        </div>
    `;

    try {
        const data = await fetchApi(`/api/weather/preview?city=${city}`);

        previewContainer.innerHTML = `
            <div class="alert alert-info mb-0">
                <small class="text-muted d-block mb-2">미리보기 (${data.city})</small>
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

// 테스트 발송
async function testWeatherNotification() {
    const resultEl = document.getElementById('test-result');
    const city = document.getElementById('city-select').value;

    resultEl.innerHTML = `
        <div class="alert alert-info mb-0">
            <i class="bi bi-hourglass-split me-2"></i>테스트 발송 중...
        </div>
    `;

    try {
        const data = await fetchApi(`/api/weather/test?city=${city}`, { method: 'POST' });

        resultEl.innerHTML = `
            <div class="alert alert-success mb-0">
                <i class="bi bi-check-circle me-2"></i>${data.message}
            </div>
        `;

        // 로그 새로고침
        setTimeout(() => {
            loadLogs();
            loadWeatherStatus();
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
        const data = await fetchApi('/api/weather/logs?limit=20');

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
