// Calendar JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadCalendarStatus();
    loadCalendarSettings();
    loadLogs();

    // 활성화 토글 이벤트 리스너
    const activeToggle = document.getElementById('calendar-active-toggle');
    activeToggle.addEventListener('change', async function() {
        await toggleCalendarActive(this.checked);
    });
});

// 캘린더 모듈 상태 로드
async function loadCalendarStatus() {
    try {
        const data = await fetchApi('/api/calendar/status');

        // 활성화 상태
        const activeToggle = document.getElementById('calendar-active-toggle');
        const activeLabel = document.getElementById('active-status-label');
        activeToggle.checked = data.is_active;
        activeLabel.textContent = data.is_active ? 'Active' : 'Inactive';
        activeLabel.className = data.is_active ? 'form-check-label text-success' : 'form-check-label text-secondary';

        // Google 연동 상태
        const googleStatusEl = document.getElementById('google-connection-status');
        const googleLoginBtn = document.getElementById('google-login-btn');

        if (data.google_connected) {
            googleStatusEl.innerHTML = '<span class="badge bg-success">Connected</span>';
            googleLoginBtn.classList.add('d-none');
        } else {
            googleStatusEl.innerHTML = '<span class="badge bg-secondary">Not Connected</span>';
            googleLoginBtn.classList.remove('d-none');
        }

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
        console.error('Failed to load calendar status:', error);
        showToast('상태 정보를 불러오는데 실패했습니다', 'error');
    }
}

// 캘린더 설정 로드
async function loadCalendarSettings() {
    try {
        const data = await fetchApi('/api/settings/calendar');

        // 알림 시간 설정
        const timeInput = document.getElementById('notification-time');
        timeInput.value = data.notification_time || '08:00';

    } catch (error) {
        console.error('Failed to load calendar settings:', error);
    }
}

// 활성화 토글
async function toggleCalendarActive(isActive) {
    try {
        await fetchApi('/api/settings/calendar', {
            method: 'PUT',
            body: JSON.stringify({ is_active: isActive })
        });

        const activeLabel = document.getElementById('active-status-label');
        activeLabel.textContent = isActive ? 'Active' : 'Inactive';
        activeLabel.className = isActive ? 'form-check-label text-success' : 'form-check-label text-secondary';

        showToast(`캘린더 알림 ${isActive ? '활성화' : '비활성화'}`, 'success');

        // 상태 새로고침
        setTimeout(() => loadCalendarStatus(), 1000);

    } catch (error) {
        // 토글 상태 되돌리기
        const activeToggle = document.getElementById('calendar-active-toggle');
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

        await fetchApi('/api/settings/calendar', {
            method: 'PUT',
            body: JSON.stringify({
                notification_time: notificationTime
            })
        });

        showToast('설정이 저장되었습니다', 'success');

        // 상태 새로고침
        setTimeout(() => loadCalendarStatus(), 1000);

    } catch (error) {
        showToast('설정 저장에 실패했습니다', 'error');
    }
}

// 일정 미리보기
async function loadPreview() {
    const previewContainer = document.getElementById('calendar-preview');

    previewContainer.innerHTML = `
        <div class="text-center text-muted py-3">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">불러오는 중...</span>
        </div>
    `;

    try {
        const data = await fetchApi('/api/calendar/preview');

        previewContainer.innerHTML = `
            <div class="alert alert-info mb-0">
                <small class="text-muted d-block mb-2">오늘의 일정 (총 ${data.event_count}개)</small>
                <pre class="mb-0" style="white-space: pre-wrap; font-size: 0.9rem;">${data.message}</pre>
            </div>
        `;

    } catch (error) {
        // Google 연동이 필요한 경우
        if (error.message && error.message.includes('Google')) {
            previewContainer.innerHTML = `
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    Google 계정 연동이 필요합니다
                    <div class="mt-2">
                        <a href="/auth/google/login" class="btn btn-sm btn-danger">
                            <i class="bi bi-google me-1"></i>Google 로그인
                        </a>
                    </div>
                </div>
            `;
        } else {
            previewContainer.innerHTML = `
                <div class="alert alert-danger mb-0">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    일정을 불러오는데 실패했습니다: ${error.message}
                </div>
            `;
        }
    }
}

// 테스트 발송
async function testCalendarNotification() {
    const resultEl = document.getElementById('test-result');

    resultEl.innerHTML = `
        <div class="alert alert-info mb-0">
            <i class="bi bi-hourglass-split me-2"></i>테스트 발송 중...
        </div>
    `;

    try {
        const data = await fetchApi('/api/calendar/test', { method: 'POST' });

        resultEl.innerHTML = `
            <div class="alert alert-success mb-0">
                <i class="bi bi-check-circle me-2"></i>${data.message}
            </div>
        `;

        // 로그 새로고침
        setTimeout(() => {
            loadLogs();
            loadCalendarStatus();
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
        const data = await fetchApi('/api/calendar/logs?limit=20');

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
