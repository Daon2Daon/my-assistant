// Home JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadSchedulerStatus();
    loadModuleSummary();
    loadRecentLogs();
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

// Load module summary
async function loadModuleSummary() {
    try {
        // Load settings for active status
        const settingsData = await fetchApi('/api/settings');

        settingsData.forEach(setting => {
            const statusEl = document.getElementById(`${setting.category}-active-status`);
            if (statusEl) {
                if (setting.is_active) {
                    statusEl.className = 'badge bg-success';
                    statusEl.textContent = 'Active';
                } else {
                    statusEl.className = 'badge bg-secondary';
                    statusEl.textContent = 'Inactive';
                }
            }
        });

        // Load jobs for next run time
        const jobsData = await fetchApi('/api/scheduler/jobs');

        // Map job IDs to module categories
        const jobModuleMap = {
            'weather_daily': 'weather',
            'finance_us_daily': 'finance',
            'finance_kr_daily': 'finance',
            'calendar_daily': 'calendar'
        };

        jobsData.jobs.forEach(job => {
            const module = jobModuleMap[job.id];
            if (module) {
                const nextRunEl = document.getElementById(`${module}-next-run`);
                if (nextRunEl) {
                    nextRunEl.textContent = `다음 발송: ${formatDateTime(job.next_run_time)}`;
                }
            }
        });

        // Load reminders count
        const remindersData = await fetchApi('/api/reminders');
        const pendingCount = remindersData.reminders.filter(r => !r.is_sent).length;

        const remindersCountEl = document.getElementById('reminders-count');
        if (remindersCountEl) {
            remindersCountEl.className = pendingCount > 0 ? 'badge bg-warning' : 'badge bg-secondary';
            remindersCountEl.textContent = `${pendingCount}개`;
        }

    } catch (error) {
        console.error('Failed to load module summary:', error);
    }
}

// Load recent logs
async function loadRecentLogs() {
    const container = document.getElementById('recent-logs');

    try {
        const data = await fetchApi('/api/logs?limit=5');

        if (data.logs.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">로그가 없습니다</p>';
            return;
        }

        let html = '';
        data.logs.forEach(log => {
            const statusClass = {
                'SUCCESS': 'log-success',
                'FAIL': 'log-fail',
                'SKIP': 'log-skip'
            }[log.status] || '';

            const statusBadge = {
                'SUCCESS': '<span class="badge bg-success">SUCCESS</span>',
                'FAIL': '<span class="badge bg-danger">FAIL</span>',
                'SKIP': '<span class="badge bg-warning">SKIP</span>'
            }[log.status] || `<span class="badge bg-secondary">${log.status}</span>`;

            html += `
                <div class="log-item ${statusClass} border-bottom pb-2 mb-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <span class="badge bg-info">${log.category}</span>
                            ${statusBadge}
                        </div>
                        <small class="text-muted">${formatDateTime(log.created_at)}</small>
                    </div>
                    <div class="mt-1 text-muted small">${truncateText(log.message, 150)}</div>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = '<p class="text-danger text-center py-3">로그를 불러오는데 실패했습니다</p>';
    }
}
