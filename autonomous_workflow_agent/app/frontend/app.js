// Global state
let categoryChart = null;
let sentimentChart = null;

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
    loadRuns();
    loadAnalytics();
    loadReports();
    setupEventListeners();
});

function setupEventListeners() {
    // Workflow form submission
    document.getElementById('workflowForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await runWorkflow();
    });
}

// Workflow Functions
async function runWorkflow() {
    const btn = document.getElementById('runWorkflowBtn');
    const maxEmails = parseInt(document.getElementById('maxEmails').value);
    const generateReport = document.getElementById('generateReport').checked;

    btn.disabled = true;
    btn.textContent = 'Running...';

    try {
        const response = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                max_emails: maxEmails,
                generate_report: generateReport
            })
        });

        if (!response.ok) throw new Error('Workflow failed');

        const result = await response.json();
        alert(`Workflow ${result.status}! Run ID: ${result.run_id}`);

        // Refresh data
        loadRuns();
        loadAnalytics();
        loadReports();
    } catch (error) {
        console.error('Error:', error);
        alert('Error running workflow: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Workflow';
    }
}

async function stopRun(runId) {
    if (!confirm('Are you sure you want to stop this workflow?')) return;

    try {
        const response = await fetch(`/api/runs/${runId}/stop`, { method: 'POST' });
        if (!response.ok) throw new Error('Failed to stop workflow');

        // Refresh list
        loadRuns();
        loadAnalytics();
    } catch (error) {
        console.error('Error stopping run:', error);
        alert('Error: ' + error.message);
    }
}

// Runs Functions
async function loadRuns() {
    const container = document.getElementById('runsContainer');
    container.innerHTML = '<p class="loading">Loading...</p>';

    try {
        const response = await fetch('/api/runs?limit=10');
        if (!response.ok) throw new Error('Failed to load runs');

        const runs = await response.json();

        if (runs.length === 0) {
            container.innerHTML = '<p class="empty-state">No workflow runs yet. Click "Run Workflow" to start!</p>';
            return;
        }

        container.innerHTML = runs.map(run => `
            <div class="run-item" onclick="showRunDetails('${run.run_id}')">
                <div class="run-header">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span class="status-badge status-${run.status}">${run.status}</span>
                        ${(run.status.toLowerCase() === 'running' || run.status.toLowerCase() === 'in_progress' || run.status.toLowerCase() === 'pending') ?
                `<button onclick="event.stopPropagation(); stopRun('${run.run_id}')" class="btn-stop" style="padding: 4px 8px; font-size: 0.65rem; background: rgba(220, 53, 69, 0.2); color: #ea868f; border: 1px solid #ea868f; border-radius: 4px; cursor: pointer; text-transform: uppercase; font-weight: 700; transition: all 0.2s;">✕ Stop</button>`
                : ''}
                    </div>
                    <span class="run-id">${run.run_id.substring(0, 8)}</span>
                </div>
                <div class="run-info">
                    <div class="info-item">
                        <strong>Started:</strong> ${new Date(run.started_at).toLocaleString()}
                    </div>
                    <div class="info-item">
                        <strong>Emails:</strong> ${run.emails_processed || 0}
                    </div>
                    ${run.completed_at ? `
                        <div class="info-item">
                            <strong>Duration:</strong> ${calculateDuration(run.started_at, run.completed_at)}
                        </div>
                    ` : ''}
                </div>
                ${run.error_message ? `
                    <div class="error-message">${run.error_message}</div>
                ` : ''}
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading runs:', error);
        container.innerHTML = '<p class="error">Error loading runs. Please try again.</p>';
    }
}

async function showRunDetails(runId) {
    try {
        const response = await fetch(`/api/runs/${runId}`);
        if (!response.ok) throw new Error('Failed to load run details');

        const run = await response.json();

        document.getElementById('runDetails').innerHTML = `
            <div class="detail-section">
                <h3>Run Information</h3>
                <p><strong>Run ID:</strong> ${run.run_id}</p>
                <p><strong>Status:</strong> <span class="status-badge status-${run.status}">${run.status}</span></p>
                <p><strong>Started:</strong> ${new Date(run.started_at).toLocaleString()}</p>
                ${run.completed_at ? `<p><strong>Completed:</strong> ${new Date(run.completed_at).toLocaleString()}</p>` : ''}
                <p><strong>Emails Processed:</strong> ${run.emails_processed || 0}</p>
                ${run.report_path ? `<p><strong>Report:</strong> ${run.report_path}</p>` : ''}
                ${run.error_message ? `<p class="error-message"><strong>Error:</strong> ${run.error_message}</p>` : ''}
            </div>
        `;

        document.getElementById('runModal').style.display = 'block';
        document.body.style.overflow = 'hidden'; // Lock background scroll
    } catch (error) {
        console.error('Error loading run details:', error);
        alert('Error loading run details');
    }
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
    document.body.style.overflow = 'auto'; // Unlock background scroll
}

function calculateDuration(start, end) {
    const diff = new Date(end) - new Date(start);
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${seconds % 60}s`;
}

// Reports Functions
async function loadReports() {
    const container = document.getElementById('reportsContainer');
    container.innerHTML = '<p class="loading">Loading...</p>';

    try {
        const response = await fetch(`/api/reports?t=${new Date().getTime()}`);
        if (!response.ok) throw new Error('Failed to load reports');

        const data = await response.json();
        const reports = data.reports || [];

        if (reports.length === 0) {
            container.innerHTML = '<p class="empty-state">No reports generated yet. Run a workflow with "Generate AI Report" enabled!</p>';
            return;
        }

        container.innerHTML = reports.map(report => {
            const date = new Date(report.created_at * 1000);

            let urgencyBadge = '';
            if (report.urgency_summary) {
                const s = report.urgency_summary;
                urgencyBadge = `
                    <div class="urgency-info" style="margin-top: 8px; display: flex; align-items: center; gap: 8px;">
                        <span class="status-badge" style="background-color: ${s.color === 'red' ? '#ffebee' : s.color === 'orange' ? '#fff3e0' : '#e8f5e9'}; color: ${s.color === 'red' ? '#c62828' : s.color === 'orange' ? '#ef6c00' : '#2e7d32'}; border-color: transparent;">
                            ${s.label}
                        </span>
                        <span style="font-size: 0.8rem; color: #666;">
                            (Important: ${s.important}, Review: ${s.review})
                        </span>
                    </div>
                `;
            }

            return `
                <div class="run-item" onclick="viewReport('${report.filename}')">
                    <div class="run-header">
                        <span class="status-badge status-completed">📄 Report</span>
                        <span class="run-id">${report.filename.replace('report_', '').replace('.md', '')}</span>
                    </div>
                    ${urgencyBadge}
                    <div class="run-info" style="margin-top: 12px;">
                        <div class="info-item">
                            <strong>Created:</strong> ${date.toLocaleString()}
                        </div>
                        <div class="info-item">
                            <strong>Size:</strong> ${(report.size / 1024).toFixed(2)} KB
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Error loading reports:', error);
        container.innerHTML = '<p class="error">Error loading reports. Please try again.</p>';
    }
}

async function viewReport(filename) {
    try {
        const response = await fetch(`/api/reports/${filename}`);
        if (!response.ok) throw new Error('Failed to load report');

        const data = await response.json();

        document.getElementById('reportTitle').textContent = filename.replace('.md', '');
        document.getElementById('reportContent').innerHTML = marked.parse(data.content);
        document.getElementById('reportModal').style.display = 'block';
        document.body.style.overflow = 'hidden'; // Lock background scroll
    } catch (error) {
        console.error('Error viewing report:', error);
        alert('Error loading report: ' + error.message);
    }
}

// Analytics Functions
async function loadAnalytics() {
    try {
        const response = await fetch('/api/analytics/summary?days=7');
        if (!response.ok) throw new Error('Failed to load analytics');

        const data = await response.json();

        // Update stats
        document.getElementById('totalEmails').textContent = data.total_emails || 0;
        document.getElementById('successRate').textContent = `${Math.round(data.success_rate || 0)}%`;
        document.getElementById('totalRuns').textContent = data.total_runs || 0;
        // Convert urgency from 0.0-1.0 to 1-10 whole number
        const urgencyWhole = Math.max(1, Math.min(10, Math.round((data.avg_urgency_score || 0) * 10)));
        document.getElementById('avgUrgency').textContent = urgencyWhole;

        // Render charts
        renderCategoryChart(data.categories || {});
        renderSentimentChart(data.sentiments || {});

    } catch (error) {
        console.error('Error loading analytics:', error);
        // Set default values on error
        document.getElementById('totalEmails').textContent = '0';
        document.getElementById('successRate').textContent = '0%';
        document.getElementById('totalRuns').textContent = '0';
        document.getElementById('avgUrgency').textContent = '0.0';
    }
}

function renderCategoryChart(categories) {
    const ctx = document.getElementById('categoryChart');

    // Destroy existing chart
    if (categoryChart) {
        categoryChart.destroy();
    }

    const labels = Object.keys(categories);
    const values = Object.values(categories);

    if (labels.length === 0) {
        // Show empty state
        ctx.getContext('2d').clearRect(0, 0, ctx.width, ctx.height);
        return;
    }

    categoryChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels.map(l => l.replace(/_/g, ' ').toUpperCase()),
            datasets: [{
                data: values,
                backgroundColor: [
                    '#FF6384',
                    '#36A2EB',
                    '#FFCE56',
                    '#4BC0C0',
                    '#9966FF',
                    '#FF9F40'
                ],
                borderWidth: 2,
                borderColor: '#1e1e1e'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Email Categories',
                    color: '#C5A059',
                    font: { size: 18, weight: 'bold', family: "'Playfair Display', serif" }
                },
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#C5A059',
                        padding: 15,
                        font: { size: 13, weight: '500', family: "'Montserrat', sans-serif" },
                        boxWidth: 15,
                        boxHeight: 15
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(30, 30, 30, 0.9)',
                    titleColor: '#FFD700',
                    bodyColor: '#fff',
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 }
                }
            }
        }
    });
}

function renderSentimentChart(sentiments) {
    const ctx = document.getElementById('sentimentChart');

    // Destroy existing chart
    if (sentimentChart) {
        sentimentChart.destroy();
    }

    const labels = Object.keys(sentiments);
    const values = Object.values(sentiments);

    if (labels.length === 0) {
        ctx.getContext('2d').clearRect(0, 0, ctx.width, ctx.height);
        return;
    }

    const colors = labels.map(label => {
        if (label.toLowerCase() === 'positive') return '#4CAF50';
        if (label.toLowerCase() === 'negative') return '#F44336';
        return '#FFC107';
    });

    sentimentChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels.map(l => l.toUpperCase()),
            datasets: [{
                label: 'Email Count',
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#C5A059'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Email Sentiment Distribution',
                    color: '#C5A059',
                    font: { size: 18, weight: 'bold', family: "'Playfair Display', serif" }
                },
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(30, 30, 30, 0.9)',
                    titleColor: '#FFD700',
                    bodyColor: '#fff',
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { size: 14, weight: 'bold', family: "'Montserrat', sans-serif" },
                    bodyFont: { size: 13, family: "'Montserrat', sans-serif" }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#C5A059',
                        font: { size: 13, weight: '500', family: "'Montserrat', sans-serif" },
                        stepSize: 1
                    },
                    grid: {
                        color: 'rgba(197, 160, 89, 0.1)',
                        drawBorder: false
                    },
                    title: {
                        display: true,
                        text: 'Number of Emails',
                        color: '#C5A059',
                        font: { size: 13, weight: '600', family: "'Montserrat', sans-serif" }
                    }
                },
                x: {
                    ticks: {
                        color: '#C5A059',
                        font: { size: 13, weight: '500', family: "'Montserrat', sans-serif" }
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// Close modal when clicking outside
window.onclick = function (event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
        document.body.style.overflow = 'auto'; // Unlock background scroll
    }
}
