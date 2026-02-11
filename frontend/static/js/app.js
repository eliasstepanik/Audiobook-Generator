// API Base URL
const API_BASE = window.location.origin;

// State
let currentJobs = [];
let autoRefreshInterval = null;
let expandedJobIds = new Set(); // Track which jobs have expanded chapters

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeTabs();
    initializeForms();
    initializeFilters();
    loadStats();
    loadJobs();
    startAutoRefresh();
});

// Tab Management
function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;
            
            // Update active tab button
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            // Update active tab content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
}

// Form Handling
function initializeForms() {
    // Text form submission
    document.getElementById('text-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const title = document.getElementById('text-title').value;
        const text = document.getElementById('text-input').value;
        const enableTextProcessing = document.getElementById('text-processing').checked;
        const enableSpeakerDetection = document.getElementById('speaker-detection').checked;
        const webhookUrl = document.getElementById('webhook-url').value;
        
        try {
            const response = await fetch(`${API_BASE}/jobs`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text,
                    title: title || null,
                    enable_text_processing: enableTextProcessing,
                    enable_speaker_detection: enableSpeakerDetection,
                    webhook_url: webhookUrl || null,
                }),
            });
            
            if (!response.ok) throw new Error('Failed to create job');
            
            const job = await response.json();
            showToast('Job created successfully!', 'success');
            document.getElementById('text-form').reset();
            loadJobs();
            loadStats();
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
    
    // File form submission
    document.getElementById('file-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const title = document.getElementById('file-title').value;
        const fileInput = document.getElementById('file-input');
        const file = fileInput.files[0];
        const enableTextProcessing = document.getElementById('file-text-processing').checked;
        const enableSpeakerDetection = document.getElementById('file-speaker-detection').checked;
        const webhookUrl = document.getElementById('file-webhook-url').value;
        
        const formData = new FormData();
        formData.append('file', file);
        if (title) {
            formData.append('title', title);
        }
        formData.append('enable_text_processing', enableTextProcessing);
        formData.append('enable_speaker_detection', enableSpeakerDetection);
        if (webhookUrl) {
            formData.append('webhook_url', webhookUrl);
        }
        
        try {
            const response = await fetch(`${API_BASE}/jobs/upload`, {
                method: 'POST',
                body: formData,
            });
            
            if (!response.ok) throw new Error('Failed to upload file');
            
            const job = await response.json();
            showToast('File uploaded and job created!', 'success');
            document.getElementById('file-form').reset();
            loadJobs();
            loadStats();
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });

    // Book (ZIP) form submission
    document.getElementById('book-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        const title = document.getElementById('book-title').value;
        const fileInput = document.getElementById('book-input');
        const file = fileInput.files[0];
        const enableTextProcessing = document.getElementById('book-text-processing').checked;
        const enableSpeakerDetection = document.getElementById('book-speaker-detection').checked;
        const webhookUrl = document.getElementById('book-webhook-url').value;

        const formData = new FormData();
        formData.append('file', file);
        if (title) {
            formData.append('title', title);
        }
        formData.append('enable_text_processing', enableTextProcessing);
        formData.append('enable_speaker_detection', enableSpeakerDetection);
        if (webhookUrl) {
            formData.append('webhook_url', webhookUrl);
        }

        try {
            const response = await fetch(`${API_BASE}/jobs/upload-book`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || 'Failed to upload book');
            }

            const job = await response.json();
            const chapterCount = job.child_jobs ? job.child_jobs.length : 0;
            showToast(`Book uploaded! ${chapterCount} chapters queued.`, 'success');
            document.getElementById('book-form').reset();
            loadJobs();
            loadStats();
        } catch (error) {
            showToast(`Error: ${error.message}`, 'error');
        }
    });
}

// Filters
function initializeFilters() {
    document.getElementById('status-filter').addEventListener('change', loadJobs);
    document.getElementById('refresh-btn').addEventListener('click', () => {
        loadJobs();
        loadStats();
        showToast('Refreshed', 'info');
    });
}

// Load Statistics
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        const stats = await response.json();
        
        document.getElementById('stat-total').textContent = stats.total_jobs;
        document.getElementById('stat-pending').textContent = stats.pending;
        document.getElementById('stat-processing').textContent = stats.processing;
        document.getElementById('stat-review').textContent = stats.awaiting_review || 0;
        document.getElementById('stat-completed').textContent = stats.completed;
        document.getElementById('stat-failed').textContent = stats.failed;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Load Jobs
async function loadJobs() {
    const statusFilter = document.getElementById('status-filter').value;
    const jobsList = document.getElementById('jobs-list');
    
    try {
        let url = `${API_BASE}/jobs?limit=100`;
        if (statusFilter) {
            url += `&status=${statusFilter}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        currentJobs = data.jobs;
        
        if (currentJobs.length === 0) {
            jobsList.innerHTML = '<p class="empty-state">No jobs found</p>';
            return;
        }
        
        jobsList.innerHTML = currentJobs.map(job => renderJob(job)).join('');
        
        // Add event listeners to job action buttons
        addJobActionListeners();
        
    } catch (error) {
        jobsList.innerHTML = '<p class="error">Failed to load jobs</p>';
        console.error('Failed to load jobs:', error);
    }
}

// Render Job Card
function renderJob(job) {
    const statusClass = `status-${job.status}`;
    const createdDate = new Date(job.created_at).toLocaleString();
    const isBatch = job.is_batch;

    let actionsHTML = '';

    if (job.status === 'completed') {
        if (isBatch) {
            actionsHTML = `
                <button class="btn btn-success" onclick="downloadFullAudiobook('${job.job_id}')">
                    ⬇️ Full Audiobook
                </button>
                <button class="btn btn-secondary" onclick="downloadBook('${job.job_id}', '${escapeAttr(job.title || 'audiobook')}.zip')">
                    ⬇️ Download ZIP
                </button>
            `;
        } else {
            actionsHTML = `
                <button class="btn btn-success" onclick="downloadJob('${job.job_id}', '${escapeAttr(job.output_filename)}')">
                    ⬇️ Download
                </button>
            `;
        }
    }

    if (job.status === 'awaiting_review') {
        actionsHTML += `
            <button class="btn btn-primary" onclick="openCharacterReview('${job.job_id}')">
                Review Characters
            </button>
        `;
    }

    if (job.status === 'pending' || job.status === 'processing') {
        actionsHTML += `
            <button class="btn btn-danger" onclick="deleteJob('${job.job_id}')">
                ✖️ Cancel
            </button>
        `;
    }

    if (job.status === 'failed' || job.status === 'cancelled' || job.status === 'completed') {
        actionsHTML += `
            <button class="btn btn-secondary" onclick="deleteJob('${job.job_id}')">
                🗑️ Delete
            </button>
        `;
    }

    let progressHTML = '';
    if (job.status === 'processing' || job.status === 'pending') {
        const progressMessage = job.progress_message || 'Processing...';
        progressHTML = `
            <div class="job-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${job.progress}%"></div>
                </div>
                <div class="progress-text">${job.progress}% - ${escapeHtml(progressMessage)}</div>
            </div>
        `;
    }

    // Awaiting review: show detected characters summary
    let reviewHTML = '';
    if (job.status === 'awaiting_review') {
        if (job.detected_characters && job.detected_characters.length > 0) {
            const chars = job.detected_characters;
            const charSummary = chars.map(c =>
                `<div class="review-char-row">
                    <span class="review-char-name">${escapeHtml(c.name)}</span>
                    <span class="review-char-traits">${escapeHtml(c.voice_characteristics || c.description || '')}</span>
                </div>`
            ).join('');

            reviewHTML = `
                <div class="review-prompt">
                    <div class="review-prompt-header">
                        ${chars.length} character${chars.length !== 1 ? 's' : ''} detected — review before continuing
                    </div>
                    <div class="review-char-list">
                        ${charSummary}
                    </div>
                </div>
            `;
        } else {
            reviewHTML = `
                <div class="review-prompt">
                    <div class="review-prompt-header">
                        ${escapeHtml(job.progress_message || 'Characters detected — click Review to continue')}
                    </div>
                </div>
            `;
        }
    }

    let errorHTML = '';
    if (job.error_message) {
        errorHTML = `
            <div class="error-message">
                <strong>Error:</strong> ${escapeHtml(job.error_message.substring(0, 200))}
            </div>
        `;
    }

    // Batch type badge
    const typeBadge = isBatch
        ? '<span class="batch-badge">BOOK</span>'
        : '';

    // Child jobs (chapters) for batch jobs
    let childJobsHTML = '';
    if (isBatch && job.child_jobs && job.child_jobs.length > 0) {
        const chapterRows = job.child_jobs.map((child, idx) => {
            const childStatus = `status-${child.status}`;
            const chapterProgress = child.status === 'processing'
                ? `<div class="chapter-progress-bar"><div class="progress-fill" style="width: ${child.progress}%"></div></div>`
                : '';
            const downloadBtn = child.status === 'completed'
                ? `<button class="btn btn-sm btn-success chapter-download-btn" onclick="downloadChapter('${job.job_id}', ${child.chapter_index}, '${escapeAttr(child.output_filename || `chapter_${idx + 1}.mp3`)}')">⬇️</button>`
                : '';
            return `
                <div class="chapter-row">
                    <span class="chapter-index">${idx + 1}.</span>
                    <span class="chapter-name">${escapeHtml(child.title || child.input_filename || 'Chapter')}</span>
                    <span class="job-status ${childStatus}">${child.status}</span>
                    ${chapterProgress}
                    ${downloadBtn}
                </div>
            `;
        }).join('');

        const completedCount = job.child_jobs.filter(c => c.status === 'completed').length;
        const totalCount = job.child_jobs.length;

        const isExpanded = expandedJobIds.has(job.job_id);
        childJobsHTML = `
            <div class="child-jobs-section">
                <div class="child-jobs-header" onclick="toggleChildJobs(this, '${job.job_id}')">
                    Chapters (${completedCount}/${totalCount} done) ${isExpanded ? '▴' : '▾'}
                </div>
                <div class="child-jobs-list" style="display: ${isExpanded ? 'block' : 'none'};">
                    ${chapterRows}
                </div>
            </div>
        `;
    }

    return `
        <div class="job-item ${isBatch ? 'batch-job' : ''}">
            <div class="job-header">
                <div>
                    <div class="job-title">${typeBadge} ${escapeHtml(job.title || job.input_filename || 'Untitled Audiobook')}</div>
                    <div class="job-id">ID: ${job.job_id}</div>
                </div>
                <div class="job-status ${statusClass}">${job.status}</div>
            </div>
            
            ${progressHTML}
            ${reviewHTML}
            ${childJobsHTML}
            
            <div class="job-details">
                <div class="job-detail">
                    <span class="job-detail-label">Created</span>
                    <span class="job-detail-value">${createdDate}</span>
                </div>
                <div class="job-detail">
                    <span class="job-detail-label">Text Processing</span>
                    <span class="job-detail-value">${job.enable_text_processing ? 'Enabled' : 'Disabled'}</span>
                </div>
                <div class="job-detail">
                    <span class="job-detail-label">Speaker Detection</span>
                    <span class="job-detail-value">${job.enable_speaker_detection ? 'Enabled' : 'Disabled'}</span>
                </div>
            </div>
            
            ${errorHTML}
            
            <div class="job-actions">
                ${actionsHTML}
            </div>
        </div>
    `;
}

function toggleChildJobs(header, jobId) {
    const list = header.nextElementSibling;
    if (list.style.display === 'none') {
        list.style.display = 'block';
        header.textContent = header.textContent.replace('▾', '▴');
        expandedJobIds.add(jobId);
    } else {
        list.style.display = 'none';
        header.textContent = header.textContent.replace('▴', '▾');
        expandedJobIds.delete(jobId);
    }
}

// Job Actions
function addJobActionListeners() {
    // Event delegation is handled via onclick attributes in renderJob
}

async function downloadJob(jobId, filename) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/download`);
        
        if (!response.ok) {
            throw new Error('Failed to download file');
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showToast('Download started', 'success');
    } catch (error) {
        showToast(`Download failed: ${error.message}`, 'error');
    }
}

async function downloadBook(jobId, filename) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/download-book`);

        if (!response.ok) {
            throw new Error('Failed to download book');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('Book download started', 'success');
    } catch (error) {
        showToast(`Download failed: ${error.message}`, 'error');
    }
}

async function downloadFullAudiobook(jobId) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/download-full`);

        if (!response.ok) {
            throw new Error('Failed to download full audiobook');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // Get filename from content-disposition header or use default
        const contentDisposition = response.headers.get('content-disposition');
        let filename = 'audiobook_complete.mp3';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
            if (match) filename = match[1];
        }
        
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('Full audiobook download started', 'success');
    } catch (error) {
        showToast(`Download failed: ${error.message}`, 'error');
    }
}

async function downloadChapter(jobId, chapterIndex, filename) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/chapters/${chapterIndex}/download`);

        if (!response.ok) {
            throw new Error('Failed to download chapter');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast(`Chapter ${chapterIndex + 1} download started`, 'success');
    } catch (error) {
        showToast(`Download failed: ${error.message}`, 'error');
    }
}

async function deleteJob(jobId) {
    if (!confirm('Are you sure you want to delete/cancel this job?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
            method: 'DELETE',
        });
        
        if (!response.ok) throw new Error('Failed to delete job');
        
        showToast('Job deleted', 'success');
        loadJobs();
        loadStats();
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Auto Refresh
function startAutoRefresh() {
    // Refresh every 5 seconds
    autoRefreshInterval = setInterval(() => {
        loadJobs();
        loadStats();
    }, 5000);
}

// Toast Notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            container.removeChild(toast);
        }, 300);
    }, 3000);
}

// Utility Functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    return text.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// =========================================================================
// Character Review
// =========================================================================

async function openCharacterReview(jobId) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/characters`);
        if (!response.ok) throw new Error('Failed to load characters');
        const data = await response.json();

        showCharacterModal(jobId, data.characters);
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

function showCharacterModal(jobId, characters) {
    // Remove existing modal
    const existing = document.getElementById('character-modal');
    if (existing) existing.remove();

    const characterRows = characters.map((char, idx) => `
        <div class="character-card" data-character-id="${char.id}">
            <div class="character-header">
                <span class="character-number">${idx + 1}</span>
                <input type="text" class="char-name" value="${escapeAttr(char.name)}" placeholder="Name">
                <span class="voice-badge ${char.has_voice_clone ? 'clone' : 'generated'}">
                    ${char.has_voice_clone ? 'CLONE' : 'GENERATED'}
                </span>
            </div>
            <div class="character-fields">
                <div class="field-group">
                    <label>Description</label>
                    <input type="text" class="char-description" value="${escapeAttr(char.description || '')}" placeholder="Brief character description">
                </div>
                <div class="field-group">
                    <label>Voice Characteristics</label>
                    <input type="text" class="char-voice" value="${escapeAttr(char.voice_characteristics || '')}" placeholder="e.g. Female, 25, high-pitched, fast pace">
                </div>
                <div class="field-group voice-upload-group">
                    <label>Voice Clone (WAV)</label>
                    <div class="voice-upload-row">
                        <input type="file" class="char-voice-file" accept=".wav" data-char-id="${char.id}">
                        <button class="btn btn-sm btn-secondary" onclick="uploadVoiceClone('${jobId}', '${char.id}', this)">
                            Upload
                        </button>
                        ${char.has_voice_clone ? `<button class="btn btn-sm btn-danger" onclick="removeVoiceClone('${jobId}', '${char.id}', this)">Remove</button>` : ''}
                    </div>
                </div>
                <div class="field-group">
                    <label>Reference Text <span class="field-hint">(transcript of the WAV sample for better voice cloning)</span></label>
                    <textarea class="char-ref-text" data-char-id="${char.id}" rows="2" placeholder="Type the exact words spoken in the voice sample...">${escapeAttr(char.ref_text || '')}</textarea>
                </div>
            </div>
        </div>
    `).join('');

    const modal = document.createElement('div');
    modal.id = 'character-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Review Characters</h2>
                <button class="modal-close" onclick="closeCharacterModal()">&times;</button>
            </div>
            <div class="modal-body">
                <p class="modal-subtitle">Edit character details or upload voice clone WAV files. Click Confirm to continue processing.</p>
                <div class="characters-list">
                    ${characterRows}
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeCharacterModal()">Cancel</button>
                <button class="btn btn-primary" onclick="saveAndConfirmCharacters('${jobId}')">
                    Save & Confirm
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

function closeCharacterModal() {
    const modal = document.getElementById('character-modal');
    if (modal) modal.remove();
}

async function uploadVoiceClone(jobId, characterId, btn) {
    const card = btn.closest('.character-card');
    const fileInput = card.querySelector(`.char-voice-file[data-char-id="${characterId}"]`);
    const file = fileInput.files[0];

    if (!file) {
        showToast('Select a WAV file first', 'error');
        return;
    }

    const refTextInput = card.querySelector(`.char-ref-text[data-char-id="${characterId}"]`);
    const refText = refTextInput ? refTextInput.value.trim() : '';

    const formData = new FormData();
    formData.append('file', file);
    if (refText) {
        formData.append('ref_text', refText);
    }

    try {
        btn.disabled = true;
        btn.textContent = 'Uploading...';

        const response = await fetch(`${API_BASE}/jobs/${jobId}/characters/${characterId}/voice-clone`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Upload failed');
        }

        showToast(`Voice clone uploaded for ${characterId}`, 'success');

        // Update badge
        const badge = card.querySelector('.voice-badge');
        badge.className = 'voice-badge clone';
        badge.textContent = 'CLONE';

        btn.textContent = 'Upload';
        btn.disabled = false;
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
        btn.textContent = 'Upload';
        btn.disabled = false;
    }
}

async function removeVoiceClone(jobId, characterId, btn) {
    try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}/characters/${characterId}/voice-clone`, {
            method: 'DELETE',
        });

        if (!response.ok) throw new Error('Failed to remove voice clone');

        showToast('Voice clone removed', 'success');

        // Update badge
        const card = btn.closest('.character-card');
        const badge = card.querySelector('.voice-badge');
        badge.className = 'voice-badge generated';
        badge.textContent = 'GENERATED';
        btn.remove();
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

async function saveAndConfirmCharacters(jobId) {
    const modal = document.getElementById('character-modal');
    const cards = modal.querySelectorAll('.character-card');

    const characters = Array.from(cards).map(card => ({
        id: card.dataset.characterId,
        name: card.querySelector('.char-name').value,
        description: card.querySelector('.char-description').value,
        voice_characteristics: card.querySelector('.char-voice').value,
        ref_text: card.querySelector('.char-ref-text')?.value?.trim() || '',
    }));

    try {
        // Save edited characters
        const saveResponse = await fetch(`${API_BASE}/jobs/${jobId}/characters`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(characters),
        });

        if (!saveResponse.ok) throw new Error('Failed to save characters');

        // Confirm and resume
        const confirmResponse = await fetch(`${API_BASE}/jobs/${jobId}/confirm`, {
            method: 'POST',
        });

        if (!confirmResponse.ok) throw new Error('Failed to confirm');

        showToast('Characters confirmed! Processing will resume.', 'success');
        closeCharacterModal();
        loadJobs();
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}
