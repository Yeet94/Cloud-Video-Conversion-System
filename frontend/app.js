/**
 * Video Converter Frontend Application
 * Handles file upload, job tracking, and downloads
 */

// API Configuration
// Nginx (in Docker) proxies /api to the backend
const API_BASE = '/api';

// DOM Elements
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const outputFormat = document.getElementById('outputFormat');
const jobsContainer = document.getElementById('jobsContainer');
const refreshBtn = document.getElementById('refreshBtn');
const systemStatus = document.getElementById('systemStatus');
const uploadModal = document.getElementById('uploadModal');
const uploadProgress = document.getElementById('uploadProgress');
const progressText = document.getElementById('progressText');

// State
let selectedFile = null;
let jobs = [];
let pollingInterval = null;

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    checkSystemHealth();
    loadJobs();
    startPolling();
});

function initializeEventListeners() {
    // File input
    uploadZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadZone.addEventListener('dragover', handleDragOver);
    uploadZone.addEventListener('dragleave', handleDragLeave);
    uploadZone.addEventListener('drop', handleDrop);

    // Upload button
    uploadBtn.addEventListener('click', handleUpload);

    // Refresh button
    refreshBtn.addEventListener('click', () => {
        refreshBtn.querySelector('svg').style.animation = 'spin 1s linear';
        loadJobs().then(() => {
            setTimeout(() => {
                refreshBtn.querySelector('svg').style.animation = '';
            }, 1000);
        });
    });
}

// ============================================
// File Handling
// ============================================

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) selectFile(file);
}

function handleDragOver(e) {
    e.preventDefault();
    uploadZone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadZone.classList.remove('dragover');

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('video/')) {
        selectFile(file);
    }
}

function selectFile(file) {
    selectedFile = file;
    uploadZone.classList.add('has-file');
    uploadBtn.disabled = false;

    // Update UI to show selected file
    const existingInfo = uploadZone.querySelector('.file-info');
    if (existingInfo) existingInfo.remove();

    const fileInfo = document.createElement('div');
    fileInfo.className = 'file-info';
    fileInfo.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
        </svg>
        <div class="file-details">
            <div class="file-name">${file.name}</div>
            <div class="file-size">${formatFileSize(file.size)}</div>
        </div>
    `;
    uploadZone.appendChild(fileInfo);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// ============================================
// Upload Flow
// ============================================

async function handleUpload() {
    if (!selectedFile) return;

    showModal();

    try {
        // Step 1: Request upload URL
        updateProgress(10, 'Requesting upload URL...');
        const uploadData = await requestUploadUrl(selectedFile.name);

        // Step 2: Upload file to MinIO
        updateProgress(20, 'Uploading video...');
        await uploadFile(uploadData.upload_url, selectedFile);

        // Step 3: Create conversion job
        updateProgress(80, 'Creating conversion job...');
        await createJob(uploadData.object_path, outputFormat.value);

        // Step 4: Complete
        updateProgress(100, 'Job created successfully!');

        setTimeout(() => {
            hideModal();
            resetUploadZone();
            loadJobs();
        }, 1000);

    } catch (error) {
        console.error('Upload failed:', error);
        updateProgress(0, `Error: ${error.message}`);
        setTimeout(hideModal, 3000);
    }
}

async function requestUploadUrl(filename) {
    const response = await fetch(`${API_BASE}/upload/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filename: filename,
            content_type: 'video/mp4'
        })
    });

    if (!response.ok) {
        throw new Error('Failed to get upload URL');
    }

    return response.json();
}

async function uploadFile(url, file) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 60) + 20;
                updateProgress(percent, `Uploading... ${Math.round(e.loaded / e.total * 100)}%`);
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                console.log('Upload successful!', xhr.status);
                resolve();
            } else {
                console.error('Upload failed:', xhr.status, xhr.statusText, xhr.responseText);
                reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
            }
        });

        xhr.addEventListener('error', (e) => {
            console.error('Upload network error:', e);
            reject(new Error('Upload failed: Network error'));
        });

        xhr.open('PUT', url);
        xhr.setRequestHeader('Content-Type', file.type || 'video/mp4');
        console.log('Uploading to:', url);
        xhr.send(file);
    });
}

async function createJob(inputPath, format) {
    const response = await fetch(`${API_BASE}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            input_path: inputPath,
            output_format: format
        })
    });

    if (!response.ok) {
        throw new Error('Failed to create job');
    }

    return response.json();
}

// ============================================
// Job Management
// ============================================

async function loadJobs() {
    try {
        const response = await fetch(`${API_BASE}/jobs?limit=50`);
        if (!response.ok) throw new Error('Failed to load jobs');

        jobs = await response.json();
        renderJobs();
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

function renderJobs() {
    if (jobs.length === 0) {
        jobsContainer.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                    <line x1="7" y1="2" x2="7" y2="22"></line>
                    <line x1="17" y1="2" x2="17" y2="22"></line>
                    <line x1="2" y1="12" x2="22" y2="12"></line>
                </svg>
                <p>No conversion jobs yet</p>
                <span>Upload a video to get started</span>
            </div>
        `;
        return;
    }

    jobsContainer.innerHTML = jobs.map(job => createJobCard(job)).join('');

    // Attach download handlers
    document.querySelectorAll('.download-btn').forEach(btn => {
        btn.addEventListener('click', () => handleDownload(btn.dataset.jobId));
    });
}

function createJobCard(job) {
    const statusClass = job.status.toLowerCase();
    const inputFile = job.input_path.split('/').pop();
    const createdAt = new Date(job.created_at).toLocaleString();
    const conversionTime = job.conversion_time_ms
        ? `Converted in ${(job.conversion_time_ms / 1000).toFixed(1)}s`
        : '';

    return `
        <div class="job-card" data-job-id="${job.id}">
            <div class="job-header">
                <span class="job-id">${job.id.slice(0, 8)}...</span>
                <span class="job-status ${statusClass}">
                    <span class="job-status-dot"></span>
                    ${job.status}
                </span>
            </div>
            <div class="job-info">
                <span class="job-path">${inputFile}</span>
                <span class="job-format">Output: ${job.output_format.toUpperCase()}</span>
                <span class="job-time">${createdAt} ${conversionTime ? '• ' + conversionTime : ''}</span>
                ${job.error_message ? `<span class="job-error" style="color: var(--error);">${job.error_message}</span>` : ''}
            </div>
            ${job.status === 'completed' ? `
                <div class="job-actions">
                    <button class="download-btn" data-job-id="${job.id}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        Download
                    </button>
                </div>
            ` : ''}
        </div>
    `;
}

async function handleDownload(jobId) {
    try {
        const response = await fetch(`${API_BASE}/download/${jobId}`);
        if (!response.ok) throw new Error('Failed to get download URL');

        const data = await response.json();

        // Open download URL in new tab
        window.open(data.download_url, '_blank');
    } catch (error) {
        console.error('Download failed:', error);
        alert('Failed to download file. Please try again.');
    }
}

// ============================================
// Polling
// ============================================

function startPolling() {
    pollingInterval = setInterval(() => {
        // Only poll if there are pending/processing jobs
        const hasActiveJobs = jobs.some(j =>
            j.status === 'pending' || j.status === 'processing'
        );

        if (hasActiveJobs) {
            loadJobs();
        }
    }, 3000);
}

// ============================================
// System Health
// ============================================

async function checkSystemHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();

        if (data.status === 'healthy') {
            systemStatus.classList.add('healthy');
            systemStatus.classList.remove('unhealthy');
            systemStatus.querySelector('.status-text').textContent = 'System Healthy';
        } else {
            systemStatus.classList.add('unhealthy');
            systemStatus.classList.remove('healthy');
            systemStatus.querySelector('.status-text').textContent = 'System Degraded';
        }
    } catch (error) {
        systemStatus.classList.add('unhealthy');
        systemStatus.classList.remove('healthy');
        systemStatus.querySelector('.status-text').textContent = 'System Offline';
    }
}

// Check health every 30 seconds
setInterval(checkSystemHealth, 30000);

// ============================================
// Modal
// ============================================

function showModal() {
    uploadModal.classList.add('active');
}

function hideModal() {
    uploadModal.classList.remove('active');
    uploadProgress.style.width = '0%';
}

function updateProgress(percent, text) {
    uploadProgress.style.width = `${percent}%`;
    progressText.textContent = text;
}

// ============================================
// Utility
// ============================================

function resetUploadZone() {
    selectedFile = null;
    fileInput.value = '';
    uploadZone.classList.remove('has-file');
    uploadBtn.disabled = true;

    const fileInfo = uploadZone.querySelector('.file-info');
    if (fileInfo) fileInfo.remove();
}

// Add CSS animation for refresh spinner
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);
