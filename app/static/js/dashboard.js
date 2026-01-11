// Dashboard JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadSchedulerStatus();
    loadAuthStatus();
    loadSettings();
    loadJobs();
    loadLogs();
});

// Load scheduler status
async function loadSchedulerStatus() {
    try {
        const data = await fetchApi('/api/scheduler/status');
        const statusEl = document.getElementById('scheduler-status');

        if (data.is_running) {
            statusEl.className = 'badge bg-success';
            statusEl.textContent = 'Running';
        } else {
            statusEl.className = 'badge bg-danger';
            statusEl.textContent = 'Stopped';
        }
    } catch (error) {
        document.getElementById('scheduler-status').textContent = 'Error';
    }
}

// Load auth status
async function loadAuthStatus() {
    try {
        const data = await fetchApi('/api/dashboard/auth-status');

        // Kakao
        const kakaoStatus = document.getElementById('kakao-status');
        const kakaoBtn = document.getElementById('kakao-login-btn');

        if (data.kakao_connected) {
            kakaoStatus.className = 'badge bg-success';
            kakaoStatus.textContent = 'Connected';
            kakaoBtn.classList.add('d-none');
        } else {
            kakaoStatus.className = 'badge bg-secondary';
            kakaoStatus.textContent = 'Not Connected';
            kakaoBtn.classList.remove('d-none');
        }

        // Google
        const googleStatus = document.getElementById('google-status');
        const googleBtn = document.getElementById('google-login-btn');

        if (data.google_connected) {
            googleStatus.className = 'badge bg-success';
            googleStatus.textContent = 'Connected';
            googleBtn.classList.add('d-none');
        } else {
            googleStatus.className = 'badge bg-secondary';
            googleStatus.textContent = 'Not Connected';
            googleBtn.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Failed to load auth status:', error);
    }
}

// Load settings for toggles
async function loadSettings() {
    try {
        const data = await fetchApi('/api/settings');

        // Set toggle states
        data.forEach(setting => {
            const toggle = document.getElementById(`${setting.category}-toggle`);
            if (toggle) {
                toggle.checked = setting.is_active;
            }
        });

        // Add toggle event listeners
        document.querySelectorAll('.form-check-input[data-category]').forEach(toggle => {
            toggle.addEventListener('change', async function() {
                const category = this.dataset.category;
                const isActive = this.checked;

                try {
                    await fetchApi(`/api/settings/${category}`, {
                        method: 'PUT',
                        body: JSON.stringify({ is_active: isActive })
                    });
                    showToast(`${category} notification ${isActive ? 'enabled' : 'disabled'}`, 'success');
                } catch (error) {
                    this.checked = !isActive; // Revert
                    showToast('Failed to update setting', 'error');
                }
            });
        });
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

// Load scheduled jobs
async function loadJobs() {
    const container = document.getElementById('jobs-list');

    try {
        const data = await fetchApi('/api/scheduler/jobs');

        if (data.jobs.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">No jobs scheduled</p>';
            return;
        }

        let html = '';
        data.jobs.forEach(job => {
            html += `
                <div class="job-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <span class="job-id">${job.id}</span>
                            <span class="job-time ms-2">${formatDateTime(job.next_run_time)}</span>
                        </div>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteJob('${job.id}')">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">Failed to load jobs</p>';
    }
}

// Load recent logs
async function loadLogs() {
    const container = document.getElementById('logs-list');

    try {
        const data = await fetchApi('/api/logs?limit=20');

        if (data.logs.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">No logs yet</p>';
            return;
        }

        let html = '';
        data.logs.forEach(log => {
            const statusClass = {
                'SUCCESS': 'log-success',
                'FAIL': 'log-fail',
                'SKIP': 'log-skip'
            }[log.status] || '';

            html += `
                <div class="log-item ${statusClass}">
                    <div class="d-flex justify-content-between">
                        <span class="log-category">${log.category}</span>
                        <span class="log-time">${formatDateTime(log.created_at)}</span>
                    </div>
                    <div class="mt-1">${truncateText(log.message, 100)}</div>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">Failed to load logs</p>';
    }
}

// Delete job
async function deleteJob(jobId) {
    if (!confirm(`Delete job "${jobId}"?`)) return;

    try {
        await fetchApi(`/api/scheduler/jobs/${jobId}`, { method: 'DELETE' });
        showToast('Job deleted', 'success');
        loadJobs();
    } catch (error) {
        showToast('Failed to delete job', 'error');
    }
}

// Test notification
async function testNotification(type) {
    const resultEl = document.getElementById('test-result');
    resultEl.innerHTML = '<div class="alert alert-info"><i class="bi bi-hourglass-split me-2"></i>Sending test notification...</div>';

    try {
        const data = await fetchApi(`/api/scheduler/test/${type}`, { method: 'POST' });
        resultEl.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle me-2"></i>${data.message}</div>`;
        setTimeout(() => loadLogs(), 2000);
    } catch (error) {
        resultEl.innerHTML = `<div class="alert alert-danger"><i class="bi bi-x-circle me-2"></i>${error.message}</div>`;
    }
}
