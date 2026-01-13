// Reminders JavaScript

let deleteReminderId = null;

document.addEventListener('DOMContentLoaded', function() {
    loadReminders();
    setupForm();
    setupFilter();
    setupDeleteModal();
    setMinDateTime();
});

// Set minimum date to today
function setMinDateTime() {
    const now = new Date();
    const minDate = now.toISOString().split('T')[0];
    document.getElementById('target_date').min = minDate;

    // Set default values to tomorrow 09:00
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    document.getElementById('target_date').value = tomorrow.toISOString().split('T')[0];
    document.getElementById('target_time').value = '09:00';
}

// Setup form submission
function setupForm() {
    const form = document.getElementById('reminder-form');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        const messageContent = document.getElementById('message_content').value.trim();
        const targetDate = document.getElementById('target_date').value;
        const targetTime = document.getElementById('target_time').value;

        if (!messageContent || !targetDate || !targetTime) {
            showFormResult('Please fill in all fields', 'warning');
            return;
        }

        // Combine date and time and convert to ISO format with timezone
        // Create a date object in local timezone
        const localDateTime = new Date(`${targetDate}T${targetTime}`);

        // Validate datetime
        if (isNaN(localDateTime.getTime())) {
            showFormResult('Invalid date or time', 'danger');
            return;
        }

        // Check if the datetime is in the future
        if (localDateTime <= new Date()) {
            showFormResult('Scheduled time must be in the future', 'warning');
            return;
        }

        // Convert to ISO string (UTC)
        const isoDatetime = localDateTime.toISOString();

        try {
            const data = await fetchApi('/api/reminders', {
                method: 'POST',
                body: JSON.stringify({
                    message_content: messageContent,
                    target_datetime: isoDatetime
                })
            });

            showFormResult('Reminder created successfully!', 'success');
            form.reset();
            setMinDateTime();
            loadReminders();
        } catch (error) {
            showFormResult(error.message || 'Failed to create reminder', 'danger');
        }
    });
}

// Show form result message
function showFormResult(message, type) {
    const resultEl = document.getElementById('form-result');
    resultEl.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show">
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`;
}

// Setup filter change
function setupFilter() {
    document.getElementById('filter-status').addEventListener('change', function() {
        loadReminders();
    });
}

// Load reminders
async function loadReminders() {
    const tbody = document.getElementById('reminders-table');
    const noReminders = document.getElementById('no-reminders');
    const filterValue = document.getElementById('filter-status').value;

    tbody.innerHTML = `
        <tr>
            <td colspan="5" class="text-center text-muted py-4">
                <div class="spinner-border spinner-border-sm" role="status"></div>
                <span class="ms-2">Loading...</span>
            </td>
        </tr>
    `;

    try {
        let url = '/api/reminders';
        if (filterValue !== '') {
            url += `?is_sent=${filterValue}`;
        }

        const data = await fetchApi(url);

        if (data.length === 0) {
            tbody.innerHTML = '';
            noReminders.classList.remove('d-none');
            return;
        }

        noReminders.classList.add('d-none');

        let html = '';
        data.forEach(reminder => {
            const statusBadge = reminder.is_sent
                ? '<span class="badge bg-success">Sent</span>'
                : '<span class="badge bg-warning">Pending</span>';

            const isPast = new Date(reminder.target_datetime) < new Date();
            const rowClass = reminder.is_sent ? '' : (isPast ? 'table-danger' : '');

            html += `
                <tr class="${rowClass}">
                    <td>${reminder.reminder_id}</td>
                    <td>${truncateText(reminder.message_content, 50)}</td>
                    <td>${formatDateTime(reminder.target_datetime)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        ${!reminder.is_sent ? `
                            <button class="btn btn-sm btn-outline-danger" onclick="showDeleteModal(${reminder.reminder_id})">
                                <i class="bi bi-trash"></i>
                            </button>
                        ` : ''}
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-danger py-4">
                    Failed to load reminders
                </td>
            </tr>
        `;
    }
}

// Setup delete modal
function setupDeleteModal() {
    document.getElementById('confirm-delete').addEventListener('click', async function() {
        if (!deleteReminderId) return;

        try {
            await fetchApi(`/api/reminders/${deleteReminderId}`, { method: 'DELETE' });
            showToast('Reminder deleted', 'success');
            loadReminders();
        } catch (error) {
            showToast('Failed to delete reminder', 'error');
        }

        bootstrap.Modal.getInstance(document.getElementById('deleteModal')).hide();
        deleteReminderId = null;
    });
}

// Show delete confirmation modal
function showDeleteModal(id) {
    deleteReminderId = id;
    const modal = new bootstrap.Modal(document.getElementById('deleteModal'));
    modal.show();
}
