// Enhanced Audiobook Generator Frontend with Detailed Progress
const API_BASE = '';
const REFRESH_INTERVAL = 2000; // 2 seconds

let refreshTimer = null;
let selectedJobDetails = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadJobs();
    loadStats();
    startAutoRefresh();
});

function initEventListeners() {
    // Tab switching
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.addEventListener('click', (e) => switchTab(e.target.dataset.tab));
    });

    // Forms
    document.getElementById('text-form').addEventListener('submit', handleTextSubmit);
    document.getElementById('file-form').addEventListener('submit', handleFileSubmit);
    
    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        loadJobs();
        loadStats();
    });
    
    // Filter
    document.getElementById('status-filter').addEventListener('change', loadJobs);
    
    // Close modal on outside click
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            closeModal();
        }
    });
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');
}

// Job submission
async function handleTextSubmit(e) {
    e.preventDefault();
    
    const text = document.getElementById('text-input').value;
    const enableTextProcessing = document.getElementById('text-processing').checked;
    const enableSpeakerDetection = document.getElementById('speaker-detection').checked;
    const webhookUrl = document.getElementById('webhook-url').value;
    
    try {
        const response = await fetch(`${API_BASE}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                enable_text_processing: enableTextProcessing,
                enable_speaker_detection: enableSpeakerDetection,
                webhook_url: webhookUrl || null
            })
        });
        
        if (!response.ok) throw new Error('Failed to create job');
        
        const data = await response.json();
        showToast('Job created successfully!', 'success');
        document.getElementById('text-input').value = '';
        loadJobs();
        loadStats();
    } catch (error) {
        showToast('Error creating job: ' + error.message, 'error');
    }
}

async function handleFileSubmit(e) {
    e.preventDefault();
    
    const fileInput = document.getElementById('file-input');
    const file = fileInput.files[0];
    const enableTextProcessing = document.getElementById('file-text-processing').checked;
    const enableSpeakerDetection = document.getElementById('file-speaker-detection').checked;
    const webhookUrl = document.getElementById('file-webhook-url').value;
    
    if (!file) {
        showToast('Please select a file', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('enable_text_processing', enableTextProcessing);
    formData.append('enable_speaker_detection', enableSpeakerDetection);
    if (webhookUrl) formData.append('webhook_url', webhookUrl);
    
    try {
        const response = await fetch(`${API_BASE}/jobs/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) throw new Error('Failed to upload file');
        
        const data = await response.json();
        showToast('File uploaded and job created!', 'success');
        fileInput.value = '';
        loadJobs();
        loadStats();
    } catch (error) {
        showToast('Error uploading file: ' + error.message, 'error');
    }
}

// Load jobs
async function loadJobs() {
    try {
        const statusFilter = document.getElementById('status-filter').value;
        const url = statusFilter 
            ? `${API_BASE}/jobs?status=${statusFilter}&limit=100`
            : `${API_BASE}/jobs?limit=100`;
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load jobs');
        
        const jobs = await response.json();
        displayJobs(jobs);
    } catch (error) {
        document.getElementById('jobs-list').innerHTML = 
            `<p class="error">Error loading jobs: ${error.message}</p>`;
    }
}

// Display jobs with enhanced details
function displayJobs(jobs) {
    const container = document.getElementById('jobs-list');
    
    if (jobs.length === 0) {
        container.innerHTML = '<p class="empty">No jobs found</p>';
        return;
    }
    
    container.innerHTML = jobs.map(job => createJobCard(job)).join('');
    
    // Attach event listeners
    jobs.forEach(job => {
        const card = document.getElementById(`job-${job.job_id}`);
        if (card) {
            card.querySelector('.job-card-header').addEventListener('click', () => {
                toggleJobDetails(job.job_id);
            });
            
            const deleteBtn = card.querySelector('.btn-delete');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteJob(job.job_id);
                });
            }
            
            const downloadBtn = card.querySelector('.btn-download');
            if (downloadBtn) {
                downloadBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    downloadJob(job.job_id);
                });
            }
            
            const detailsBtn = card.querySelector('.btn-details');
            if (detailsBtn) {
                detailsBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showDetailedProgress(job);
                });
            }
        }
    });
}

function createJobCard(job) {
    const statusClass = `status-${job.status}`;
    const statusEmoji = {
        'pending': '⏳',
        'processing': '⚙️',
        'completed': '✅',
        'failed': '❌',
        'cancelled': '🚫'
    }[job.status] || '❓';
    
    const progressBar = job.status === 'processing' 
        ? `<div class="progress-bar">
               <div class="progress-fill" style="width: ${job.progress}%"></div>
               <span class="progress-text">${job.progress}%</span>
           </div>`
        : '';
    
    const progressMessage = job.progress_message 
        ? `<div class="progress-message">${escapeHtml(job.progress_message)}</div>`
        : '';
    
    const errorMessage = job.error_message 
        ? `<div class="error-message">❌ ${escapeHtml(job.error_message)}</div>`
        : '';
    
    // Parse progress message for details
    const detailsPreview = parseProgressDetails(job.progress_message);
    
    const actions = job.status === 'completed'
        ? `<button class="btn btn-success btn-download">⬇️ Download</button>`
        : job.status === 'processing'
        ? `<button class="btn btn-info btn-details">📊 Details</button>`
        : '';
    
    const deleteBtn = (job.status === 'pending' || job.status === 'failed' || job.status === 'cancelled')
        ? `<button class="btn btn-danger btn-delete">🗑️ Delete</button>`
        : job.status === 'processing'
        ? `<button class="btn btn-warning btn-delete">⏹️ Cancel</button>`
        : '';
    
    return `
        <div class="job-card ${statusClass}" id="job-${job.job_id}">
            <div class="job-card-header">
                <div class="job-title">
                    <span class="status-emoji">${statusEmoji}</span>
                    <span class="job-name">${job.input_filename || 'Text Input'}</span>
                    <span class="job-status ${statusClass}">${job.status}</span>
                </div>
                <div class="job-meta">
                    <span class="job-id">ID: ${job.job_id.substring(0, 8)}</span>
                    <span class="job-time">${formatDate(job.created_at)}</span>
                </div>
            </div>
            
            ${progressBar}
            ${progressMessage}
            ${detailsPreview}
            ${errorMessage}
            
            <div class="job-config">
                ${job.enable_text_processing ? '<span class="badge">🤖 Ollama</span>' : ''}
                ${job.enable_speaker_detection ? '<span class="badge">🎭 Speakers</span>' : ''}
                ${job.webhook_url ? '<span class="badge">🔔 Webhook</span>' : ''}
            </div>
            
            <div class="job-actions">
                ${actions}
                ${deleteBtn}
            </div>
        </div>
    `;
}

// Parse progress message to extract details
function parseProgressDetails(message) {
    if (!message) return '';
    
    const details = [];
    
    // Extract batch info
    const batchMatch = message.match(/Processing batch (\d+)\/(\d+)/i);
    if (batchMatch) {
        details.push(`📄 Batch ${batchMatch[1]}/${batchMatch[2]}`);
    }
    
    // Extract speaker count
    const speakerMatch = message.match(/Detected (\d+) speaker/i);
    if (speakerMatch) {
        details.push(`🎭 ${speakerMatch[1]} speaker(s)`);
    }
    
    // Extract segment info
    const segmentMatch = message.match(/segment (\d+)\/(\d+)/i);
    if (segmentMatch) {
        details.push(`🎵 Segment ${segmentMatch[1]}/${segmentMatch[2]}`);
    }
    
    // Extract voice generation info
    const voiceMatch = message.match(/voice for (.+)/i);
    if (voiceMatch) {
        details.push(`🎤 Voice: ${voiceMatch[1]}`);
    }
    
    if (details.length > 0) {
        return `<div class="details-preview">${details.join(' • ')}</div>`;
    }
    
    return '';
}

// Toggle job details expansion
function toggleJobDetails(jobId) {
    const card = document.getElementById(`job-${jobId}`);
    if (card) {
        card.classList.toggle('expanded');
    }
}

// Show detailed progress modal
function showDetailedProgress(job) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>📊 Job Progress Details</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="detail-section">
                    <h3>Job Information</h3>
                    <table class="detail-table">
                        <tr><td><strong>Job ID:</strong></td><td>${job.job_id}</td></tr>
                        <tr><td><strong>Status:</strong></td><td>${job.status}</td></tr>
                        <tr><td><strong>Progress:</strong></td><td>${job.progress}%</td></tr>
                        <tr><td><strong>Created:</strong></td><td>${formatDate(job.created_at)}</td></tr>
                        ${job.started_at ? `<tr><td><strong>Started:</strong></td><td>${formatDate(job.started_at)}</td></tr>` : ''}
                        ${job.completed_at ? `<tr><td><strong>Completed:</strong></td><td>${formatDate(job.completed_at)}</td></tr>` : ''}
                    </table>
                </div>
                
                <div class="detail-section">
                    <h3>Current Status</h3>
                    <div class="status-message">${job.progress_message || 'Waiting...'}</div>
                </div>
                
                ${job.progress_details ? renderProgressDetails(job.progress_details) : ''}
                
                <div class="detail-section">
                    <h3>Configuration</h3>
                    <ul>
                        <li>Text Processing: ${job.enable_text_processing ? '✅ Enabled' : '❌ Disabled'}</li>
                        <li>Speaker Detection: ${job.enable_speaker_detection ? '✅ Enabled' : '❌ Disabled'}</li>
                        <li>Webhook: ${job.webhook_url ? `✅ ${job.webhook_url}` : '❌ Not set'}</li>
                    </ul>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);
}

function renderProgressDetails(details) {
    let html = '';
    
    if (details.batches) {
        html += `
            <div class="detail-section">
                <h3>📄 Text Batches (${details.batches.length})</h3>
                <div class="batches-list">
                    ${details.batches.map((batch, idx) => `
                        <div class="batch-item batch-${batch.status}">
                            <div class="batch-header">
                                <span class="batch-index">Batch ${idx + 1}</span>
                                <span class="batch-status">${batch.status}</span>
                            </div>
                            <div class="batch-preview">${batch.text_preview}</div>
                            <div class="batch-meta">${batch.length} characters</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    if (details.speakers) {
        html += `
            <div class="detail-section">
                <h3>🎭 Detected Speakers (${details.speakers.length})</h3>
                <div class="speakers-list">
                    ${details.speakers.map(speaker => `
                        <div class="speaker-item">
                            <div class="speaker-name">${speaker.name}</div>
                            <div class="speaker-desc">${speaker.description}</div>
                            <div class="speaker-voice">${speaker.voice_characteristics}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    if (details.segments) {
        html += `
            <div class="detail-section">
                <h3>🎵 Audio Segments (${details.segments.length})</h3>
                <div class="segments-list">
                    ${details.segments.map((seg, idx) => `
                        <div class="segment-item segment-${seg.status}">
                            <span class="segment-index">${idx + 1}</span>
                            <span class="segment-speaker">${seg.speaker}</span>
                            <span class="segment-text">${seg.text_preview}</span>
                            <span class="segment-status">${seg.status}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    return html;
}

function closeModal() {
    const modal = document.querySelector('.modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => modal.remove(), 300);
    }
}

// Load stats
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        if (!response.ok) throw new Error('Failed to load stats');
        
        const stats = await response.json();
        document.getElementById('stat-total').textContent = stats.total;
        document.getElementById('stat-pending').textContent = stats.by_status.pending || 0;
        document.getElementById('stat-processing').textContent = stats.by_status.processing || 0;
        document.getElementById('stat-completed').textContent = stats.by_status.completed || 0;
        document.getElementById('stat-failed').textContent = stats.by_status.failed || 0;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Download job
async function downloadJob(jobId) {
    window.location.href = `${API_BASE}/jobs/${jobId}/download`;
}

// Delete job
async function deleteJob(jobId) {
    if (!confirm('Are you sure you want to delete this job?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete job');
        
        showToast('Job deleted successfully', 'success');
        loadJobs();
        loadStats();
    } catch (error) {
        showToast('Error deleting job: ' + error.message, 'error');
    }
}

// Auto refresh
function startAutoRefresh() {
    refreshTimer = setInterval(() => {
        loadJobs();
        loadStats();
    }, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

// Toast notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Utilities
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
