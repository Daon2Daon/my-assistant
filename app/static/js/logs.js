// Logs JavaScript

let currentPage = 1;
let currentFilters = {
    category: '',
    status: '',
    limit: 50
};

document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadLogs();
});

// 통계 로드
async function loadStats() {
    try {
        const data = await fetchApi('/api/logs/stats');

        // 전체 로그
        document.getElementById('total-logs').textContent = data.total_logs || 0;

        // 상태별 통계
        document.getElementById('success-count').textContent = data.by_status.SUCCESS || 0;
        document.getElementById('fail-count').textContent = data.by_status.FAIL || 0;
        document.getElementById('skip-count').textContent = data.by_status.SKIP || 0;

    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// 로그 로드
async function loadLogs(page = 1) {
    currentPage = page;
    const tableBody = document.getElementById('logs-table-body');
    const countInfo = document.getElementById('logs-count-info');

    // 로딩 표시
    tableBody.innerHTML = `
        <tr>
            <td colspan="5" class="text-center text-muted py-4">
                <div class="spinner-border spinner-border-sm" role="status"></div>
                <span class="ms-2">Loading...</span>
            </td>
        </tr>
    `;

    try {
        const offset = (page - 1) * currentFilters.limit;
        let url = `/api/logs?limit=${currentFilters.limit}&offset=${offset}`;

        if (currentFilters.category) {
            url += `&category=${currentFilters.category}`;
        }
        if (currentFilters.status) {
            url += `&status=${currentFilters.status}`;
        }

        const data = await fetchApi(url);

        // 카운트 정보 표시
        countInfo.textContent = `총 ${data.total}개 중 ${data.count}개 표시`;

        if (data.logs.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center text-muted py-4">
                        로그가 없습니다
                    </td>
                </tr>
            `;
            document.getElementById('pagination').innerHTML = '';
            return;
        }

        // 로그 테이블 렌더링
        let html = '';
        data.logs.forEach(log => {
            const statusClass = {
                'SUCCESS': 'text-success',
                'FAIL': 'text-danger',
                'SKIP': 'text-warning'
            }[log.status] || '';

            const statusBadge = {
                'SUCCESS': '<span class="badge bg-success">SUCCESS</span>',
                'FAIL': '<span class="badge bg-danger">FAIL</span>',
                'SKIP': '<span class="badge bg-warning">SKIP</span>'
            }[log.status] || `<span class="badge bg-secondary">${log.status}</span>`;

            const categoryBadge = {
                'weather': '<span class="badge bg-info">Weather</span>',
                'finance': '<span class="badge bg-success">Finance</span>',
                'calendar': '<span class="badge bg-primary">Calendar</span>',
                'memo': '<span class="badge bg-warning">Memo</span>'
            }[log.category] || `<span class="badge bg-secondary">${log.category}</span>`;

            html += `
                <tr>
                    <td>${categoryBadge}</td>
                    <td>${statusBadge}</td>
                    <td>${truncateText(log.message, 100)}</td>
                    <td><small>${formatDateTime(log.created_at)}</small></td>
                    <td>
                        <button class="btn btn-sm btn-outline-secondary" onclick='showLogDetail(${JSON.stringify(log)})'>
                            <i class="bi bi-eye"></i>
                        </button>
                    </td>
                </tr>
            `;
        });

        tableBody.innerHTML = html;

        // 페이지네이션 렌더링
        renderPagination(data.total, currentFilters.limit, page);

    } catch (error) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-danger py-4">
                    로그를 불러오는데 실패했습니다
                </td>
            </tr>
        `;
        console.error('Failed to load logs:', error);
    }
}

// 페이지네이션 렌더링
function renderPagination(total, limit, currentPage) {
    const totalPages = Math.ceil(total / limit);
    const paginationEl = document.getElementById('pagination');

    if (totalPages <= 1) {
        paginationEl.innerHTML = '';
        return;
    }

    let html = '';

    // 이전 버튼
    html += `
        <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadLogs(${currentPage - 1}); return false;">이전</a>
        </li>
    `;

    // 페이지 번호
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    if (startPage > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="loadLogs(1); return false;">1</a></li>`;
        if (startPage > 2) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="loadLogs(${i}); return false;">${i}</a>
            </li>
        `;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        html += `<li class="page-item"><a class="page-link" href="#" onclick="loadLogs(${totalPages}); return false;">${totalPages}</a></li>`;
    }

    // 다음 버튼
    html += `
        <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="loadLogs(${currentPage + 1}); return false;">다음</a>
        </li>
    `;

    paginationEl.innerHTML = html;
}

// 필터 적용
function applyFilters() {
    currentFilters.category = document.getElementById('category-filter').value;
    currentFilters.status = document.getElementById('status-filter').value;
    currentFilters.limit = parseInt(document.getElementById('limit-select').value);

    loadLogs(1);
}

// 필터 초기화
function resetFilters() {
    document.getElementById('category-filter').value = '';
    document.getElementById('status-filter').value = '';
    document.getElementById('limit-select').value = '50';

    currentFilters = {
        category: '',
        status: '',
        limit: 50
    };

    loadLogs(1);
}

// 로그 상세 보기
function showLogDetail(log) {
    // 모달에 데이터 표시
    const categoryBadge = {
        'weather': '<span class="badge bg-info">Weather</span>',
        'finance': '<span class="badge bg-success">Finance</span>',
        'calendar': '<span class="badge bg-primary">Calendar</span>',
        'memo': '<span class="badge bg-warning">Memo</span>'
    }[log.category] || `<span class="badge bg-secondary">${log.category}</span>`;

    const statusBadge = {
        'SUCCESS': '<span class="badge bg-success">SUCCESS</span>',
        'FAIL': '<span class="badge bg-danger">FAIL</span>',
        'SKIP': '<span class="badge bg-warning">SKIP</span>'
    }[log.status] || `<span class="badge bg-secondary">${log.status}</span>`;

    document.getElementById('modal-category').innerHTML = categoryBadge;
    document.getElementById('modal-status').innerHTML = statusBadge;
    document.getElementById('modal-time').textContent = formatDateTime(log.created_at);
    document.getElementById('modal-message').textContent = log.message;

    // 모달 표시
    const modal = new bootstrap.Modal(document.getElementById('logDetailModal'));
    modal.show();
}
