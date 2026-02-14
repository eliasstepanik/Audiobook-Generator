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
    loadVoiceLibrary();
    startAutoRefresh();
});

// Voice Library Management
async function loadVoiceLibrary() {
    try {
        const response = await fetch(`${API_BASE}/voices`);
        const voices = await response.json();
        
        const container = document.getElementById('voice-presets-list');
        if (!container) return;
        
        if (voices.length === 0) {
            container.innerHTML = '<p class="no-voices">No voice presets created yet. Generate one below!</p>';
            return;
        }
        
        container.innerHTML = voices.map(voice => `
            <div class="voice-preset-card" data-voice-id="${escapeAttr(voice.voice_id)}">
                <div class="voice-info">
                    <h4>${escapeHtml(voice.name)}</h4>
                    <p class="voice-description">${escapeHtml(voice.description || '')}</p>
                    <div class="voice-tags">
                        ${voice.gender ? `<span class="tag">${escapeHtml(voice.gender)}</span>` : ''}
                        ${voice.age ? `<span class="tag">${voice.age} years</span>` : ''}
                        ${voice.is_system ? '<span class="tag system">System</span>' : '<span class="tag user">Custom</span>'}
                    </div>
                </div>
                <div class="voice-actions">
                    <button class="btn btn-sm" onclick="playVoicePreview('${escapeAttr(voice.voice_id)}')">
                        Preview
                    </button>
                    ${!voice.is_system ? `
                        <button class="btn btn-sm btn-danger" onclick="deleteVoicePreset('${escapeAttr(voice.voice_id)}')">
                            Delete
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to load voice library:', error);
    }
}

async function generateVoicePreset() {
    const name = document.getElementById('voice-name').value.trim();
    const description = document.getElementById('voice-description').value.trim();
    const gender = document.getElementById('voice-gender').value;
    const age = document.getElementById('voice-age').value;
    const pitch = document.getElementById('voice-pitch').value;
    const pace = document.getElementById('voice-pace').value;
    const sampleText = document.getElementById('voice-sample-text').value.trim();
    
    if (!name) {
        alert('Please enter a name for the voice preset');
        return;
    }
    
    // Build voice characteristics string
    const characteristics = [];
    if (gender) characteristics.push(gender.charAt(0).toUpperCase() + gender.slice(1));
    if (age) characteristics.push(`${age} years old`);
    if (pitch) characteristics.push(`${pitch} pitch`);
    if (pace) characteristics.push(`${pace} pace`);
    characteristics.push('clear articulation');
    
    const voiceCharacteristics = characteristics.join(', ');
    
    // Show loading state
    const btn = document.querySelector('#voice-generator button[type="submit"]');
    const originalText = btn.textContent;
    btn.textContent = 'Generating...';
    btn.disabled = true;
    
    try {
        const formData = new URLSearchParams();
        formData.append('name', name);
        formData.append('description', description);
        formData.append('gender', gender);
        formData.append('age', age);
        formData.append('voice_characteristics', voiceCharacteristics);
        formData.append('sample_text', sampleText || 'Hello, welcome to this audiobook. I hope you enjoy listening.');
        
        const response = await fetch(`${API_BASE}/voices/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate voice');
        }
        
        const result = await response.json();
        alert(`Voice "${name}" generated successfully!`);
        
        // Clear form
        document.getElementById('voice-name').value = '';
        document.getElementById('voice-description').value = '';
        document.getElementById('voice-sample-text').value = '';
        
        // Reload voice library
        loadVoiceLibrary();
        
    } catch (error) {
        console.error('Failed to generate voice:', error);
        alert('Failed to generate voice: ' + error.message);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function playVoicePreview(voiceId) {
    try {
        const audio = new Audio(`${API_BASE}/voices/${voiceId}/preview`);
        audio.play();
    } catch (error) {
        console.error('Failed to play voice preview:', error);
        alert('Failed to play voice preview');
    }
}

async function deleteVoicePreset(voiceId) {
    if (!confirm('Are you sure you want to delete this voice preset?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/voices/${voiceId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete voice');
        }
        
        loadVoiceLibrary();
    } catch (error) {
        console.error('Failed to delete voice:', error);
        alert('Failed to delete voice: ' + error.message);
    }
}

async function uploadVoiceFile() {
    const name = document.getElementById('upload-voice-name').value.trim();
    const description = document.getElementById('upload-voice-description').value.trim();
    const fileInput = document.getElementById('upload-voice-file');
    const refText = document.getElementById('upload-voice-ref-text').value.trim();
    
    if (!name) {
        alert('Please enter a name for the voice preset');
        return;
    }
    
    if (!fileInput.files || !fileInput.files[0]) {
        alert('Please select a voice file to upload');
        return;
    }
    
    const btn = document.querySelector('#voice-uploader button[type="submit"]');
    const originalText = btn.textContent;
    btn.textContent = 'Uploading...';
    btn.disabled = true;
    
    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('description', description);
        formData.append('reference_text', refText);
        formData.append('file', fileInput.files[0]);
        
        const response = await fetch(`${API_BASE}/voices`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to upload voice');
        }
        
        alert(`Voice "${name}" uploaded successfully!`);
        
        // Clear form
        document.getElementById('upload-voice-name').value = '';
        document.getElementById('upload-voice-description').value = '';
        document.getElementById('upload-voice-file').value = '';
        document.getElementById('upload-voice-ref-text').value = '';
        
        // Reload voice library
        loadVoiceLibrary();
        
    } catch (error) {
        console.error('Failed to upload voice:', error);
        alert('Failed to upload voice: ' + error.message);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// Show Create Voice Modal
function showCreateVoiceModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'create-voice-modal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 600px;">
            <div class="modal-header">
                <h2>Create New Voice</h2>
                <button class="close-modal" onclick="closeCreateVoiceModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="create-voice-tabs">
                    <button class="create-voice-tab active" onclick="switchCreateVoiceTab('generate')">Generate Voice</button>
                    <button class="create-voice-tab" onclick="switchCreateVoiceTab('upload')">Upload Voice File</button>
                </div>
                
                <!-- Generate Voice Tab -->
                <div id="generate-voice-tab" class="create-voice-panel active">
                    <p>Use AI to generate a new voice based on characteristics:</p>
                    <div class="form-group">
                        <label>Voice Name *</label>
                        <input type="text" id="gen-voice-name" placeholder="e.g., Professional Narrator">
                    </div>
                    <div class="form-group">
                        <label>Gender</label>
                        <select id="gen-voice-gender">
                            <option value="male">Male</option>
                            <option value="female">Female</option>
                            <option value="neutral">Neutral</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Age</label>
                        <input type="number" id="gen-voice-age" value="30" min="5" max="90">
                    </div>
                    <div class="form-group">
                        <label>Voice Characteristics *</label>
                        <input type="text" id="gen-voice-characteristics" placeholder="e.g., warm, clear, professional narrator voice">
                    </div>
                    <div class="form-group">
                        <label>Sample Text (what the voice will say)</label>
                        <textarea id="gen-voice-sample" rows="2" placeholder="Hello, welcome to this audiobook.">Hello, welcome to this audiobook.</textarea>
                    </div>
                    <button class="btn-primary" onclick="generateVoiceFromModal()">Generate Voice</button>
                </div>
                
                <!-- Upload Voice Tab -->
                <div id="upload-voice-tab" class="create-voice-panel" style="display: none;">
                    <p>Upload a voice file (.wav for audio reference, .pt for pre-trained voice model):</p>
                    <div class="form-group">
                        <label>Voice Name *</label>
                        <input type="text" id="upl-voice-name" placeholder="e.g., My Custom Voice">
                    </div>
                    <div class="form-group">
                        <label>Description</label>
                        <input type="text" id="upl-voice-description" placeholder="Brief description of this voice">
                    </div>
                    <div class="form-group">
                        <label>Voice File * (.wav or .pt)</label>
                        <input type="file" id="upl-voice-file" accept=".wav,.pt">
                    </div>
                    <div class="form-group" id="upl-ref-text-group">
                        <label>Reference Text (for .wav files - what is spoken in the audio)</label>
                        <textarea id="upl-voice-ref-text" rows="2" placeholder="The exact words spoken in the uploaded audio..."></textarea>
                    </div>
                    <button class="btn-primary" onclick="uploadVoiceFromModal()">Upload Voice</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function closeCreateVoiceModal() {
    const modal = document.getElementById('create-voice-modal');
    if (modal) modal.remove();
}

function switchCreateVoiceTab(tab) {
    document.querySelectorAll('.create-voice-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.create-voice-panel').forEach(p => {
        p.classList.remove('active');
        p.style.display = 'none';
    });
    
    if (tab === 'generate') {
        document.querySelector('.create-voice-tab:first-child').classList.add('active');
        document.getElementById('generate-voice-tab').style.display = 'block';
        document.getElementById('generate-voice-tab').classList.add('active');
    } else {
        document.querySelector('.create-voice-tab:last-child').classList.add('active');
        document.getElementById('upload-voice-tab').style.display = 'block';
        document.getElementById('upload-voice-tab').classList.add('active');
    }
}

async function generateVoiceFromModal() {
    const name = document.getElementById('gen-voice-name').value.trim();
    const gender = document.getElementById('gen-voice-gender').value;
    const age = document.getElementById('gen-voice-age').value;
    const characteristics = document.getElementById('gen-voice-characteristics').value.trim();
    const sampleText = document.getElementById('gen-voice-sample').value.trim();
    
    if (!name || !characteristics) {
        alert('Please fill in name and voice characteristics');
        return;
    }
    
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'Generating...';
    btn.disabled = true;
    
    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('gender', gender);
        formData.append('age', age);
        formData.append('voice_characteristics', characteristics);
        formData.append('sample_text', sampleText || 'Hello, welcome to this audiobook.');
        
        const response = await fetch(`${API_BASE}/voices/generate`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate voice');
        }
        
        alert(`Voice "${name}" generated successfully!`);
        closeCreateVoiceModal();
        loadVoiceLibrary();
        
    } catch (error) {
        console.error('Failed to generate voice:', error);
        alert('Failed to generate voice: ' + error.message);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function uploadVoiceFromModal() {
    const name = document.getElementById('upl-voice-name').value.trim();
    const description = document.getElementById('upl-voice-description').value.trim();
    const fileInput = document.getElementById('upl-voice-file');
    const refText = document.getElementById('upl-voice-ref-text').value.trim();
    
    if (!name || !fileInput.files.length) {
        alert('Please provide a name and select a file');
        return;
    }
    
    const file = fileInput.files[0];
    const isPt = file.name.toLowerCase().endsWith('.pt');
    
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'Uploading...';
    btn.disabled = true;
    
    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('description', description);
        formData.append('file', file);
        if (!isPt && refText) {
            formData.append('reference_text', refText);
        }
        
        const response = await fetch(`${API_BASE}/voices`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to upload voice');
        }
        
        alert(`Voice "${name}" uploaded successfully!`);
        closeCreateVoiceModal();
        loadVoiceLibrary();
        
    } catch (error) {
        console.error('Failed to upload voice:', error);
        alert('Failed to upload voice: ' + error.message);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

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
        // Load characters and voice presets in parallel
        const [charactersResponse, presetsResponse] = await Promise.all([
            fetch(`${API_BASE}/jobs/${jobId}/characters`),
            fetch(`${API_BASE}/voices`)
        ]);
        
        if (!charactersResponse.ok) throw new Error('Failed to load characters');
        const charactersData = await charactersResponse.json();
        
        // Voice presets are optional - don't fail if not available
        let voicePresets = [];
        if (presetsResponse.ok) {
            const presetsData = await presetsResponse.json();
            voicePresets = presetsData.voice_presets || [];
        }

        showCharacterModal(jobId, charactersData.characters, voicePresets);
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    }
}

function showCharacterModal(jobId, characters, voicePresets = []) {
    // Remove existing modal
    const existing = document.getElementById('character-modal');
    if (existing) existing.remove();

    // Build voice preset options
    const presetOptions = voicePresets.length > 0
        ? voicePresets.map(p => `<option value="${p.voice_id}">${escapeHtml(p.name)}${p.gender ? ` (${p.gender})` : ''}</option>`).join('')
        : '';

    const characterRows = characters.map((char, idx) => {
        const currentPresetId = char.voice_preset_id || '';
        const voiceSource = char.has_voice_clone ? 'clone' : (char.voice_preset_id ? 'preset' : 'generated');
        const badgeText = char.has_voice_clone ? 'CLONE' : (char.voice_preset_id ? 'PRESET' : 'GENERATED');
        
        return `
        <div class="character-card" data-character-id="${char.id}">
            <div class="character-header">
                <span class="character-number">${idx + 1}</span>
                <input type="text" class="char-name" value="${escapeAttr(char.name)}" placeholder="Name">
                <span class="voice-badge ${voiceSource}">
                    ${badgeText}
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
                ${voicePresets.length > 0 ? `
                <div class="field-group">
                    <label>Use Pre-Created Voice</label>
                    <div class="voice-preset-row">
                        <select class="char-voice-preset" data-char-id="${char.id}">
                            <option value="">-- Generate new voice --</option>
                            ${presetOptions}
                        </select>
                        <button class="btn btn-sm btn-primary" onclick="assignVoicePreset('${jobId}', '${char.id}', this)">
                            Apply
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="previewVoicePreset(this)">
                            ▶ Preview
                        </button>
                    </div>
                    ${char.voice_preset_name ? `<div class="voice-preset-assigned">Currently assigned: <strong>${escapeHtml(char.voice_preset_name)}</strong></div>` : ''}
                </div>
                ` : ''}
                <div class="field-group voice-upload-group">
                    <label>Or Upload Voice File (WAV or PT)</label>
                    <div class="voice-upload-row">
                        <input type="file" class="char-voice-file" accept=".wav,.pt" data-char-id="${char.id}">
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
    `}).join('');

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
                <p class="modal-subtitle">Edit character details or upload voice files (.wav or .pt). Click Confirm to continue processing.</p>
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

async function assignVoicePreset(jobId, characterId, btn) {
    const card = btn.closest('.character-card');
    const select = card.querySelector('.char-voice-preset');
    const voicePresetId = select.value;
    
    if (!voicePresetId) {
        showToast('Select a voice preset first', 'warning');
        return;
    }
    
    try {
        btn.disabled = true;
        btn.textContent = 'Applying...';
        
        const formData = new FormData();
        formData.append('voice_preset_id', voicePresetId);
        
        const response = await fetch(`${API_BASE}/jobs/${jobId}/characters/${characterId}/assign-voice`, {
            method: 'POST',
            body: formData,
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to assign voice preset');
        }
        
        const result = await response.json();
        
        // Update badge to show preset
        const badge = card.querySelector('.voice-badge');
        badge.className = 'voice-badge preset';
        badge.textContent = 'PRESET';
        
        // Update or add "currently assigned" text
        let assignedDiv = card.querySelector('.voice-preset-assigned');
        if (!assignedDiv) {
            assignedDiv = document.createElement('div');
            assignedDiv.className = 'voice-preset-assigned';
            select.parentElement.after(assignedDiv);
        }
        assignedDiv.innerHTML = `Currently assigned: <strong>${escapeHtml(result.voice_preset_name)}</strong>`;
        
        showToast(`Voice "${result.voice_preset_name}" assigned to character`, 'success');
    } catch (error) {
        showToast(`Error: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Apply';
    }
}

async function previewVoicePreset(btn) {
    const card = btn.closest('.character-card');
    const select = card.querySelector('.char-voice-preset');
    const voicePresetId = select.value;
    
    if (!voicePresetId) {
        showToast('Select a voice preset to preview', 'warning');
        return;
    }
    
    try {
        // Check if audio preview exists, then play it
        const previewUrl = `${API_BASE}/voices/${voicePresetId}/preview`;
        
        // Create or reuse audio element
        let audio = document.getElementById('voice-preview-audio');
        if (!audio) {
            audio = document.createElement('audio');
            audio.id = 'voice-preview-audio';
            document.body.appendChild(audio);
        }
        
        audio.src = previewUrl;
        audio.play().catch(err => {
            showToast('No audio preview available for this voice', 'warning');
        });
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
