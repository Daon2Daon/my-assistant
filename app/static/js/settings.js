// Settings JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadSettingsAuthStatus();
    loadSettingsData();
    loadSettingsJobs();
    setupSettingToggles();
});

// Load auth status for settings page
async function loadSettingsAuthStatus() {
    try {
        const data = await fetchApi('/api/dashboard/auth-status');

        // Kakao
        const kakaoStatus = document.getElementById('settings-kakao-status');
        const kakaoBtn = document.getElementById('settings-kakao-btn');

        if (data.kakao_connected) {
            kakaoStatus.className = 'badge bg-success';
            kakaoStatus.textContent = 'Connected';
            kakaoBtn.textContent = 'Reconnect';
            kakaoBtn.classList.remove('btn-warning');
            kakaoBtn.classList.add('btn-outline-warning');
        } else {
            kakaoStatus.className = 'badge bg-secondary';
            kakaoStatus.textContent = 'Not Connected';
            kakaoBtn.innerHTML = '<i class="bi bi-box-arrow-in-right me-1"></i>Connect';
        }

        // Google
        const googleStatus = document.getElementById('settings-google-status');
        const googleBtn = document.getElementById('settings-google-btn');

        if (data.google_connected) {
            googleStatus.className = 'badge bg-success';
            googleStatus.textContent = 'Connected';
            googleBtn.textContent = 'Reconnect';
            googleBtn.classList.remove('btn-danger');
            googleBtn.classList.add('btn-outline-danger');
        } else {
            googleStatus.className = 'badge bg-secondary';
            googleStatus.textContent = 'Not Connected';
            googleBtn.innerHTML = '<i class="bi bi-box-arrow-in-right me-1"></i>Connect';
        }
    } catch (error) {
        console.error('Failed to load auth status:', error);
    }
}

// Load settings data
async function loadSettingsData() {
    try {
        const data = await fetchApi('/api/settings');

        data.forEach(setting => {
            // Set toggle state
            const toggle = document.getElementById(`settings-${setting.category}-toggle`);
            if (toggle) {
                toggle.checked = setting.is_active;
            }

            // Set time if available
            if (setting.notification_time) {
                const timeInput = getTimeInputForCategory(setting.category);
                if (timeInput) {
                    timeInput.value = setting.notification_time;
                }
            }
        });
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

// Get time input element for category
function getTimeInputForCategory(category) {
    const mapping = {
        'weather': 'weather-time',
        'finance': 'us-market-time',  // Finance uses US market time as primary
        'calendar': 'calendar-time'
    };
    return document.getElementById(mapping[category]);
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

// Setup setting toggles
function setupSettingToggles() {
    document.querySelectorAll('.setting-toggle').forEach(toggle => {
        toggle.addEventListener('change', async function() {
            const category = this.dataset.category;
            const isActive = this.checked;

            try {
                await fetchApi(`/api/settings/${category}`, {
                    method: 'PUT',
                    body: JSON.stringify({ is_active: isActive })
                });
                showSettingsResult(`${category} ${isActive ? 'enabled' : 'disabled'}`, 'success');
            } catch (error) {
                this.checked = !isActive;
                showSettingsResult('Failed to update setting', 'danger');
            }
        });
    });
}

// Register job
async function registerJob(type) {
    let hour, minute;

    // Get time based on type
    if (type === 'weather') {
        const time = document.getElementById('weather-time').value;
        [hour, minute] = time.split(':').map(Number);
    } else if (type === 'finance/us') {
        const time = document.getElementById('us-market-time').value;
        [hour, minute] = time.split(':').map(Number);
    } else if (type === 'finance/kr') {
        const time = document.getElementById('kr-market-time').value;
        [hour, minute] = time.split(':').map(Number);
    } else if (type === 'calendar') {
        const time = document.getElementById('calendar-time').value;
        [hour, minute] = time.split(':').map(Number);
    }

    try {
        const data = await fetchApi(`/api/scheduler/jobs/${type}?hour=${hour}&minute=${minute}`, {
            method: 'POST'
        });
        showSettingsResult(data.message, 'success');
        loadSettingsJobs();
    } catch (error) {
        showSettingsResult(error.message || 'Failed to register job', 'danger');
    }
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
