// Settings JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadSettingsAuthStatus();
    loadSettingsJobs();
    checkLoginStatus();
    loadTelegramStatus();
});

// Check login status from URL query parameters
function checkLoginStatus() {
    const urlParams = new URLSearchParams(window.location.search);

    // Kakao login status
    if (urlParams.get('kakao_login') === 'success') {
        showSettingsResult('카카오 로그인 성공', 'success');
        // Remove query parameters from URL
        window.history.replaceState({}, document.title, '/settings');
        // Reload auth status
        loadSettingsAuthStatus();
    } else if (urlParams.get('kakao_login') === 'error') {
        const message = decodeURIComponent(urlParams.get('message') || '카카오 로그인 실패');
        showSettingsResult(`카카오 로그인 실패: ${message}`, 'danger');
        window.history.replaceState({}, document.title, '/settings');
    }

    // Google login status
    if (urlParams.get('google_login') === 'success') {
        showSettingsResult('구글 로그인 성공', 'success');
        window.history.replaceState({}, document.title, '/settings');
        // Reload auth status
        loadSettingsAuthStatus();
    } else if (urlParams.get('google_login') === 'error') {
        const message = decodeURIComponent(urlParams.get('message') || '구글 로그인 실패');
        showSettingsResult(`구글 로그인 실패: ${message}`, 'danger');
        window.history.replaceState({}, document.title, '/settings');
    }
}

// Load auth status for settings page
async function loadSettingsAuthStatus() {
    try {
        const data = await fetchApi('/api/dashboard/auth-status');

        // Kakao
        const kakaoStatus = document.getElementById('settings-kakao-status');
        const kakaoConnectBtn = document.getElementById('settings-kakao-connect-btn');
        const kakaoDisconnectBtn = document.getElementById('settings-kakao-disconnect-btn');

        if (data.kakao_connected) {
            kakaoStatus.className = 'badge bg-success';
            kakaoStatus.textContent = 'Connected';
            kakaoConnectBtn.style.display = 'none';
            kakaoDisconnectBtn.style.display = 'inline-block';
        } else {
            kakaoStatus.className = 'badge bg-secondary';
            kakaoStatus.textContent = 'Not Connected';
            kakaoConnectBtn.style.display = 'inline-block';
            kakaoDisconnectBtn.style.display = 'none';
        }

        // Google
        const googleStatus = document.getElementById('settings-google-status');
        const googleConnectBtn = document.getElementById('settings-google-connect-btn');
        const googleDisconnectBtn = document.getElementById('settings-google-disconnect-btn');

        if (data.google_connected) {
            googleStatus.className = 'badge bg-success';
            googleStatus.textContent = 'Connected';
            googleConnectBtn.style.display = 'none';
            googleDisconnectBtn.style.display = 'inline-block';
        } else {
            googleStatus.className = 'badge bg-secondary';
            googleStatus.textContent = 'Not Connected';
            googleConnectBtn.style.display = 'inline-block';
            googleDisconnectBtn.style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to load auth status:', error);
    }
}

// Load registered jobs
async function loadSettingsJobs() {
    const container = document.getElementById('settings-jobs-list');

    try {
        const data = await fetchApi('/api/scheduler/jobs');

        if (data.jobs.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">No jobs registered</p>';
            return;
        }

        let html = '<div class="list-group">';
        data.jobs.forEach(job => {
            const icon = getJobIcon(job.id);
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <i class="bi ${icon} me-2"></i>
                        <strong>${job.id}</strong>
                        <small class="text-muted ms-2">Next: ${formatDateTime(job.next_run_time)}</small>
                    </div>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteSettingsJob('${job.id}')">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
            `;
        });
        html += '</div>';

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">Failed to load jobs</p>';
    }
}

// Get icon for job type
function getJobIcon(jobId) {
    if (jobId.includes('weather')) return 'bi-cloud-sun text-info';
    if (jobId.includes('us_market')) return 'bi-graph-up text-success';
    if (jobId.includes('kr_market')) return 'bi-graph-up text-success';
    if (jobId.includes('calendar')) return 'bi-calendar-event text-primary';
    if (jobId.includes('reminder')) return 'bi-bell text-warning';
    return 'bi-clock';
}

// Delete job from settings
async function deleteSettingsJob(jobId) {
    if (!confirm(`Delete job "${jobId}"?`)) return;

    try {
        await fetchApi(`/api/scheduler/jobs/${jobId}`, { method: 'DELETE' });
        showSettingsResult('Job deleted', 'success');
        loadSettingsJobs();
    } catch (error) {
        showSettingsResult('Failed to delete job', 'danger');
    }
}

// Show settings result toast
function showSettingsResult(message, type) {
    const container = document.getElementById('settings-result');
    const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';

    container.innerHTML = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    // Auto dismiss after 3 seconds
    setTimeout(() => {
        const alert = container.querySelector('.alert');
        if (alert) {
            alert.classList.remove('show');
            setTimeout(() => container.innerHTML = '', 150);
        }
    }, 3000);
}

// ========================================
// Telegram Integration Functions
// ========================================

// Load Telegram connection status
async function loadTelegramStatus() {
    try {
        const data = await fetchApi('/auth/telegram/status');

        const statusBadge = document.getElementById('settings-telegram-status');
        const connectBtn = document.getElementById('settings-telegram-connect-btn');
        const disconnectBtn = document.getElementById('settings-telegram-disconnect-btn');
        const testBtn = document.getElementById('settings-telegram-test-btn');

        if (data.telegram_connected) {
            statusBadge.className = 'badge bg-success';
            statusBadge.textContent = 'Connected';
            connectBtn.style.display = 'none';
            disconnectBtn.style.display = 'inline-block';
            testBtn.style.display = 'inline-block';
        } else {
            statusBadge.className = 'badge bg-secondary';
            statusBadge.textContent = 'Not Connected';
            connectBtn.style.display = 'inline-block';
            disconnectBtn.style.display = 'none';
            testBtn.style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to load Telegram status:', error);
    }
}

// Connect Telegram - Open modal with instructions
async function connectTelegram() {
    const modal = new bootstrap.Modal(document.getElementById('telegramModal'));
    const modalContent = document.getElementById('telegram-modal-content');

    // Show loading
    modalContent.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-info" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2 text-muted">Loading bot information...</p>
        </div>
    `;

    modal.show();

    try {
        const data = await fetchApi('/auth/telegram/start');

        modalContent.innerHTML = `
            <div class="alert alert-info mb-3">
                <i class="bi bi-info-circle me-2"></i>
                <strong>Connect to Telegram Bot</strong>
            </div>

            <div class="mb-3">
                <h6>Step 1: Start the bot</h6>
                <p class="text-muted small mb-2">Click the button below to open Telegram and start the bot:</p>
                <a href="${data.bot_url}" target="_blank" class="btn btn-info btn-sm w-100">
                    <i class="bi bi-telegram me-2"></i>Open ${data.bot_username} in Telegram
                </a>
            </div>

            <div class="mb-3">
                <h6>Step 2: Get your Chat ID</h6>
                <p class="text-muted small mb-2">Send <code>/start</code> command to the bot. The bot will reply with your Chat ID.</p>
            </div>

            <div class="mb-3">
                <h6>Step 3: Enter Chat ID</h6>
                <label for="telegram-chat-id" class="form-label">Chat ID</label>
                <input type="text" class="form-control" id="telegram-chat-id" placeholder="Enter your Chat ID">
                <div class="form-text">Example: 123456789 or -123456789</div>
            </div>

            <div class="d-grid">
                <button class="btn btn-primary" onclick="verifyTelegram()">
                    <i class="bi bi-check-circle me-2"></i>Verify and Connect
                </button>
            </div>
        `;
    } catch (error) {
        modalContent.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle me-2"></i>
                Failed to load bot information. Please try again.
            </div>
        `;
    }
}

// Verify and save Chat ID
async function verifyTelegram() {
    const chatIdInput = document.getElementById('telegram-chat-id');
    const chatId = chatIdInput.value.trim();

    if (!chatId) {
        showSettingsResult('Please enter Chat ID', 'danger');
        return;
    }

    try {
        await fetchApi('/auth/telegram/verify', {
            method: 'POST',
            body: JSON.stringify({ chat_id: chatId })
        });

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('telegramModal'));
        modal.hide();

        showSettingsResult('Telegram connected successfully', 'success');
        loadTelegramStatus();
    } catch (error) {
        showSettingsResult('Failed to verify Chat ID. Please check and try again.', 'danger');
    }
}

// Disconnect Telegram
async function disconnectTelegram() {
    if (!confirm('Are you sure you want to disconnect Telegram?')) {
        return;
    }

    try {
        await fetchApi('/auth/telegram/disconnect', { method: 'POST' });
        showSettingsResult('Telegram disconnected', 'success');
        loadTelegramStatus();
    } catch (error) {
        showSettingsResult('Failed to disconnect Telegram', 'danger');
    }
}

// Test Telegram notification
async function testTelegram() {
    try {
        const data = await fetchApi('/auth/telegram/test', { method: 'POST' });
        showSettingsResult(data.message || 'Test message sent', 'success');
    } catch (error) {
        showSettingsResult('Failed to send test message', 'danger');
    }
}

// ========================================
// Kakao & Google Disconnect Functions
// ========================================

// Disconnect Kakao
async function disconnectKakao() {
    if (!confirm('카카오톡 연동을 해제하시겠습니까?\n알림을 받을 수 없게 됩니다.')) {
        return;
    }

    try {
        await fetchApi('/auth/kakao/disconnect', { method: 'POST' });
        showSettingsResult('카카오톡 연동이 해제되었습니다', 'success');
        loadSettingsAuthStatus();
    } catch (error) {
        showSettingsResult('카카오톡 연동 해제에 실패했습니다', 'danger');
    }
}

// Disconnect Google
async function disconnectGoogle() {
    if (!confirm('구글 캘린더 연동을 해제하시겠습니까?\n캘린더 알림을 받을 수 없게 됩니다.')) {
        return;
    }

    try {
        await fetchApi('/auth/google/disconnect', { method: 'POST' });
        showSettingsResult('구글 캘린더 연동이 해제되었습니다', 'success');
        loadSettingsAuthStatus();
    } catch (error) {
        showSettingsResult('구글 캘린더 연동 해제에 실패했습니다', 'danger');
    }
}
