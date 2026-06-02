// ── Gut Health Tracker ──────────────────────────
// Persona 2: Gut Health Mode

let gutCurrentResults  = null;
let gutMealTimestamp   = null;
let gutPatientId       = localStorage.getItem('gutPatientId') || 'guest';

// ── Initialise Gut Mode ───────────────────────────
function initGutMode() {
    console.log('🦠 Gut mode initialised');
    renderGutDashboard();
}

function renderGutDashboard() {
    const container = document.getElementById('gut-mode-content');
    container.innerHTML = `
        <div class="card">
            <h2>🦠 Gut Health Tracker</h2>
            <p class="hint">
                Analyse your meals for gut bacteria impact,
                prebiotic content and FODMAP levels.
            </p>
            <div class="gut-disclaimer">
                ⚠️ AI-powered gut estimates.
                Validate with your practitioner for clinical use.
            </div>
        </div>

        <!-- Camera card -->
        <div class="card">
            <h2>📷 Take a Photo</h2>
            <div class="camera-container">
                <video id="gut-camera-preview" autoplay playsinline style="display:none"></video>
                <canvas id="gut-canvas" style="display:none"></canvas>
                <img id="gut-photo-preview" style="display:none" alt="Food photo">
                <div class="camera-placeholder" id="gut-camera-placeholder">🍽️</div>
            </div>
            <div class="button-group">
                <button class="btn-primary" onclick="gutStartCamera()">📷 Camera</button>
                <button class="btn-success" onclick="gutCapturePhoto()"
                        id="gut-capture-btn" style="display:none">✅ Capture</button>
                <button class="btn-secondary" onclick="gutUploadPhoto()">📁 Upload</button>
                <input type="file" id="gut-file-input" accept="image/*"
                       style="display:none" onchange="gutHandleFileUpload(event)">
            </div>
        </div>

        <!-- Analyze Button -->
        <button class="btn-analyze" onclick="gutAnalyzePhoto()"
                id="gut-analyze-btn" style="display:none">
            🦠 Analyze Gut Impact
        </button>

        <!-- Loading -->
        <div id="gut-loading" style="display:none" class="loading">
            <div class="spinner"></div>
            <p>Analysing gut bacteria impact...</p>
        </div>

        <!-- Results -->
        <div id="gut-results" style="display:none"></div>

        <!-- ── SCORECARD ───────────────────────── -->
        <div class="card" style="margin-top:16px">
            <div class="gut-scorecard-header">
                <h2>📊 Gut Scorecard</h2>
                <div class="scorecard-tabs">
                    <button class="scorecard-tab active"
                            onclick="switchScorecardView('daily', this)">
                        Daily
                    </button>
                    <button class="scorecard-tab"
                            onclick="switchScorecardView('weekly', this)">
                        Weekly
                    </button>
                    <button class="scorecard-tab"
                            onclick="switchScorecardView('monthly', this)">
                        Monthly
                    </button>
                </div>
            </div>
            <div id="gut-scorecard"></div>
        </div>

        <!-- History -->
        <div class="card" style="margin-top:16px">
            <h2>📅 Gut Meal History</h2>
            <div id="gut-history-list">
                <p class="hint">No gut meals logged yet.</p>
            </div>
        </div>
    `;

    loadGutScorecard();
    loadGutHistory();
}

function switchScorecardView(view, btn) {
    gutScorecardView = view;
    document.querySelectorAll('.scorecard-tab')
            .forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    loadGutScorecard();
}

// ── Camera Functions (mirrors health mode) ────────
let gutImageBase64 = null;
let gutMimeType    = 'image/jpeg';
let gutImageW      = 0;
let gutImageH      = 0;

async function gutStartCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' }
        });
        const video = document.getElementById('gut-camera-preview');
        video.srcObject = stream;
        video.style.display = 'block';
        document.getElementById('gut-photo-preview').style.display     = 'none';
        document.getElementById('gut-camera-placeholder').style.display = 'none';
        document.getElementById('gut-capture-btn').style.display        = 'block';
        document.getElementById('gut-analyze-btn').style.display        = 'none';
        gutImageBase64 = null;
    } catch (err) {
        alert('Camera access denied. Please use Upload Photo instead.');
    }
}

function gutCapturePhoto() {
    const video  = document.getElementById('gut-camera-preview');
    const canvas = document.getElementById('gut-canvas');
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    video.srcObject.getTracks().forEach(t => t.stop());
    video.style.display = 'none';

    const imageData = canvas.toDataURL('image/jpeg', 0.8);
    const preview   = document.getElementById('gut-photo-preview');
    preview.src     = imageData;
    preview.style.display = 'block';

    gutImageBase64 = imageData.split(',')[1];
    gutMimeType    = 'image/jpeg';
    gutImageW      = canvas.width;
    gutImageH      = canvas.height;

    document.getElementById('gut-capture-btn').style.display = 'none';
    document.getElementById('gut-analyze-btn').style.display = 'block';
}

function gutUploadPhoto() {
    document.getElementById('gut-file-input').click();
}

function gutHandleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    gutMimeType = file.type || 'image/jpeg';

    if (window.createImageBitmap) {
        createImageBitmap(file).then(async (bitmap) => {
            const maxW = 1200, maxH = 900;
            const ratio = Math.min(maxW / bitmap.width, maxH / bitmap.height, 1);
            const tw = Math.max(1, Math.round(bitmap.width  * ratio));
            const th = Math.max(1, Math.round(bitmap.height * ratio));

            const canvas = document.createElement('canvas');
            canvas.width  = tw;
            canvas.height = th;
            canvas.getContext('2d').drawImage(bitmap, 0, 0, tw, th);
            if (bitmap.close) bitmap.close();

            const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
            gutImageBase64 = dataUrl.split(',')[1];
            gutImageW = tw;
            gutImageH = th;

            document.getElementById('gut-photo-preview').src           = dataUrl;
            document.getElementById('gut-photo-preview').style.display = 'block';
            document.getElementById('gut-camera-placeholder').style.display = 'none';
            document.getElementById('gut-analyze-btn').style.display   = 'block';
        });
    }
}

// ── Analyze ────────────────────────────────────────
async function gutAnalyzePhoto() {
    if (!gutImageBase64) {
        alert('Please take or upload a photo first!');
        return;
    }

    document.getElementById('gut-loading').style.display  = 'block';
    document.getElementById('gut-results').style.display  = 'none';
    document.getElementById('gut-analyze-btn').style.display = 'none';

    try {
        const response = await fetch('/gut/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image:       gutImageBase64,
                mime_type:   gutMimeType,
                provider:    document.getElementById('provider-select')?.value || 'claude',
                timezone:    getUserTimezone(),
                patient_id:  gutPatientId,
                image_width: gutImageW,
                image_height: gutImageH
            })
        });

        const data = await response.json();

        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        gutCurrentResults = data;
        gutMealTimestamp  = data.timestamp;
        renderGutResults(data);

    } catch (err) {
        alert('Analysis failed: ' + err.message);
    } finally {
        document.getElementById('gut-loading').style.display = 'none';
    }
}

// ── Render Results ─────────────────────────────────
function renderGutResults(data) {
    const foods          = data.foods || [];
    const overallScore   = data.overall_gut_score || 0;
    const overallNotes   = data.overall_gut_notes || '';
    const scoreColor     = overallScore >= 7 ? '#22c55e'
                         : overallScore >= 5 ? '#f59e0b' : '#ef4444';
    const scoreEmoji     = overallScore >= 7 ? '✅' : overallScore >= 5 ? '⚠️' : '❌';

    // Build food rows
    const foodRows = foods.map(f => {
        const fodmapColor = f.fodmap === 'high'   ? '#ef4444'
                          : f.fodmap === 'medium' ? '#f59e0b' : '#22c55e';

        const bacteriaFed = (f.bacteria_fed || []).map(b => {
            const name     = typeof b === 'object' ? b.name      : b;
            const strength = typeof b === 'object' ? b.impact_strength : '';
            const mech     = typeof b === 'object' ? b.mechanism : '';
            return `<div class="bacteria-item bacteria-positive">
                        <span class="bacteria-name">✅ ${name}</span>
                        ${strength ? `<span class="bacteria-strength">${strength}/10</span>` : ''}
                        ${mech ? `<div class="bacteria-mech">${mech}</div>` : ''}
                    </div>`;
        }).join('');

        const bacteriaHarmed = (f.bacteria_harmed || []).map(b => {
            const name = typeof b === 'object' ? b.name : b;
            return `<div class="bacteria-item bacteria-negative">
                        <span class="bacteria-name">❌ ${name}</span>
                    </div>`;
        }).join('');

        const prebioticFibres = (f.prebiotic_fibres || []).length
            ? `<div class="fibre-tags">
                   ${f.prebiotic_fibres.map(fib =>
                       `<span class="fibre-tag">${fib}</span>`).join('')}
               </div>`
            : '';

        return `
            <div class="gut-food-card">
                <div class="gut-food-header">
                    <div class="gut-food-name">${f.name}</div>
                    <div class="gut-food-grams">${f.estimated_grams}g</div>
                </div>

                <div class="gut-scores-row">
                    <div class="gut-score-pill">
                        🌱 Prebiotic: <strong>${f.prebiotic_score || 0}/10</strong>
                    </div>
                    <div class="gut-score-pill">
                        🔥 Anti-inflam: <strong>${f.anti_inflammatory_score || 0}/10</strong>
                    </div>
                    <div class="gut-score-pill" style="color:${fodmapColor}">
                        FODMAP: <strong>${(f.fodmap || 'low').toUpperCase()}</strong>
                    </div>
                    ${f.probiotic
                        ? `<div class="gut-score-pill probiotic-badge">🦠 Probiotic</div>`
                        : ''}
                </div>

                ${prebioticFibres}

                ${bacteriaFed || bacteriaHarmed ? `
                    <div class="bacteria-section">
                        ${bacteriaFed    ? `<div class="bacteria-group">${bacteriaFed}</div>`    : ''}
                        ${bacteriaHarmed ? `<div class="bacteria-group">${bacteriaHarmed}</div>` : ''}
                    </div>` : ''}

                ${f.gut_notes
                    ? `<div class="gut-food-notes">💬 ${f.gut_notes}</div>`
                    : ''}
            </div>
        `;
    }).join('');

    const html = `
        <div class="card">
            <h2>🦠 Gut Impact Results</h2>
            <p class="meal-desc">${data.meal_description || ''}</p>

            <!-- Overall gut score -->
            <div class="gut-overall-score" style="border-color:${scoreColor}">
                <div class="gut-score-circle" style="background:${scoreColor}">
                    <span class="gut-score-num">${overallScore}</span>
                    <span class="gut-score-label">/ 10</span>
                </div>
                <div class="gut-score-info">
                    <div class="gut-score-title">
                        ${scoreEmoji} Overall Gut Score
                    </div>
                    <div class="gut-score-notes">${overallNotes}</div>
                </div>
            </div>

            <!-- Disclaimer -->
            <div class="gut-disclaimer">
                ⚠️ AI-powered estimates — validate with your practitioner
            </div>

            <!-- Food breakdown -->
            <div class="section-label">🥗 Food Breakdown</div>
            ${foodRows}

            <!-- Confirm / Retake -->
            <div class="confirm-bar">
                <button class="confirm-btn confirm-reject"
                        onclick="gutRejectResults()" title="Retake">
                    <span class="confirm-icon">✕</span>
                    <span class="confirm-label">Retake</span>
                </button>
                <button class="confirm-btn confirm-accept"
                        onclick="gutConfirmResults()" title="Confirm">
                    <span class="confirm-icon">✓</span>
                    <span class="confirm-label">Confirm</span>
                </button>
            </div>
        </div>
    `;

    const resultsEl = document.getElementById('gut-results');
    resultsEl.innerHTML = html;
    resultsEl.style.display = 'block';
    resultsEl.scrollIntoView({ behavior: 'smooth' });
}

// ── Confirm / Retake ───────────────────────────────
async function gutConfirmResults() {
    if (!gutCurrentResults) return;

    try {
        const response = await fetch('/gut/confirm-meal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ...gutCurrentResults,
                timezone:   getUserTimezone(),
                patient_id: gutPatientId
            })
        });

        const result = await response.json();
        if (result.error) {
            alert('Failed to save: ' + result.error);
            return;
        }

        gutCurrentResults = null;
        document.getElementById('gut-results').style.display = 'none';
        document.getElementById('gut-photo-preview').style.display     = 'none';
        document.getElementById('gut-camera-placeholder').style.display = 'block';
        document.getElementById('gut-analyze-btn').style.display        = 'none';
        gutImageBase64 = null;

        loadGutHistory();
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // Show success briefly
        const container = document.getElementById('gut-mode-content');
        const msg = document.createElement('div');
        msg.className   = 'error-banner';
        msg.textContent = '✓ Gut meal saved!';
        msg.style.cssText = 'background:#ecfdf5;color:#166534;border-color:#a7f3d0;display:block';
        container.prepend(msg);
        setTimeout(() => msg.remove(), 2000);

    } catch (err) {
        alert('Save failed: ' + err.message);
    }
}

function gutRejectResults() {
    gutCurrentResults = null;
    document.getElementById('gut-results').style.display           = 'none';
    document.getElementById('gut-photo-preview').style.display     = 'none';
    document.getElementById('gut-camera-placeholder').style.display = 'block';
    document.getElementById('gut-analyze-btn').style.display        = 'none';
    gutImageBase64 = null;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Gut History ────────────────────────────────────
async function loadGutHistory() {
    const container = document.getElementById('gut-history-list');
    if (!container) return;

    try {
        const response = await fetch(
            `/gut/history?patient_id=${gutPatientId}`
        );
        const data = await response.json();

        if (!data.length) {
            container.innerHTML = '<p class="hint">No gut meals logged yet.</p>';
            return;
        }

        container.innerHTML = [...data].reverse().map(meal => {
            const score      = meal.overall_gut_score || 0;
            const scoreColor = score >= 7 ? '#22c55e'
                             : score >= 5 ? '#f59e0b' : '#ef4444';
            const foods      = (meal.foods || [])
                .map(f => f.name).join(' · ');

            return `
                <div class="history-item">
                    <div class="history-date">
                        📅 ${meal.timestamp || ''}
                    </div>
                    <div class="history-desc">
                        ${meal.meal_description || ''}
                    </div>
                    <div class="history-foods">${foods}</div>
                    <div class="history-meta">
                        <span style="color:${scoreColor};font-weight:600">
                            🦠 Gut Score: ${score}/10
                        </span>
                    </div>
                </div>
            `;
        }).join('');

    } catch (err) {
        container.innerHTML = '<p class="hint">Could not load gut history.</p>';
    }
}
// ── Gut Scorecard ──────────────────────────────────

let gutScorecardView = 'daily'; // 'daily' | 'weekly' | 'monthly'

async function loadGutScorecard() {
    const container = document.getElementById('gut-scorecard');
    if (!container) return;

    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>Loading scorecard...</p>
        </div>`;

    try {
        let url = '';
        const today = new Date().toLocaleDateString('en-CA');

        if (gutScorecardView === 'daily') {
            url = `/gut/scorecard/daily?patient_id=${gutPatientId}&date=${today}`;
        } else if (gutScorecardView === 'weekly') {
            // Get Monday of current week
            const now    = new Date();
            const monday = new Date(now);
            monday.setDate(now.getDate() - now.getDay() + 1);
            const weekStart = monday.toLocaleDateString('en-CA');
            url = `/gut/scorecard/weekly?patient_id=${gutPatientId}&week_start=${weekStart}`;
        } else {
            const now = new Date();
            url = `/gut/scorecard/monthly?patient_id=${gutPatientId}&year=${now.getFullYear()}&month=${now.getMonth()+1}`;
        }

        const response = await fetch(url);
        const data     = await response.json();

        if (data.error) {
            container.innerHTML = `<p class="hint">Error: ${data.error}</p>`;
            return;
        }

        if (gutScorecardView === 'daily')   renderDailyScorecard(container, data);
        if (gutScorecardView === 'weekly')  renderWeeklyScorecard(container, data);
        if (gutScorecardView === 'monthly') renderMonthlyScorecard(container, data);

    } catch (err) {
        container.innerHTML = `<p class="hint">Could not load scorecard: ${err.message}</p>`;
    }
}

// ── Score color helper ─────────────────────────────
function gutScoreColor(score) {
    if (score >= 7) return '#22c55e';
    if (score >= 5) return '#f59e0b';
    return '#ef4444';
}

function gutScoreEmoji(score) {
    if (score >= 7) return '✅';
    if (score >= 5) return '⚠️';
    return '❌';
}

function fodmapColor(level) {
    if (level === 'high')   return '#ef4444';
    if (level === 'medium') return '#f59e0b';
    return '#22c55e';
}

// ── Score bar helper ───────────────────────────────
function scoreBar(score, max = 10) {
    const pct   = Math.min(100, (score / max) * 100);
    const color = gutScoreColor(score);
    return `
        <div class="gut-bar-bg">
            <div class="gut-bar-fill"
                 style="width:${pct}%;background:${color}">
            </div>
        </div>`;
}

// ── Compact bacteria row with tap-to-expand ────────
function renderBacteriaFed(bacteria_fed) {
    const entries = Object.entries(bacteria_fed);
    if (!entries.length) {
        return '<p class="hint">No bacteria fed recorded.</p>';
    }

    entries.sort((a, b) => b[1].count - a[1].count);

    return entries.map(([name, data], idx) => {
        const strengthColor = gutScoreColor(data.avg_strength);
        const pct = Math.min(100, (data.avg_strength / 10) * 100);
        const expandId = `bact-fed-${idx}`;

        return `
            <div class="bacteria-row"
                 onclick="toggleExpand('${expandId}')">
                <div class="bacteria-row-header">
                    <span class="bacteria-row-name">
                        ✅ ${name}
                    </span>
                    <div class="bacteria-row-right">
                        <span class="bacteria-row-count">
                            ${data.count}x
                        </span>
                        <span class="bacteria-strength-badge"
                              style="color:${strengthColor}">
                            ${data.avg_strength}/10
                        </span>
                        <span class="expand-arrow">›</span>
                    </div>
                </div>
                <div class="bacteria-bar-row">
                    <div class="gut-bar-bg">
                        <div class="gut-bar-fill"
                             style="width:${pct}%;
                                    background:${strengthColor}">
                        </div>
                    </div>
                </div>
                <div class="bacteria-expand" id="${expandId}">
                    <div class="bacteria-row-foods">
                        🌿 via: ${data.from_foods.join(', ')}
                    </div>
                    ${data.mechanism ? `
                        <div class="bacteria-mech">
                            💬 ${data.mechanism}
                        </div>` : ''}
                </div>
            </div>`;
    }).join('');
}

function renderBacteriaHarmed(bacteria_harmed) {
    const entries = Object.entries(bacteria_harmed);
    if (!entries.length) {
        return `<p class="hint" style="color:#22c55e">
                    ✅ None harmed today
                </p>`;
    }

    return entries.map(([name, data], idx) => {
        const expandId = `bact-harm-${idx}`;
        return `
            <div class="bacteria-row bacteria-row-harm"
                 onclick="toggleExpand('${expandId}')">
                <div class="bacteria-row-header">
                    <span class="bacteria-row-name"
                          style="color:#fca5a5">
                        ⚠️ ${name}
                    </span>
                    <div class="bacteria-row-right">
                        <span class="bacteria-row-count">
                            ${data.count}x
                        </span>
                        <span class="expand-arrow">›</span>
                    </div>
                </div>
                <div class="bacteria-expand" id="${expandId}">
                    <div class="bacteria-row-foods">
                        🍽️ via: ${data.from_foods.join(', ')}
                    </div>
                </div>
            </div>`;
    }).join('');
}

// ── Toggle expand ──────────────────────────────────
function toggleExpand(id) {
    const el  = document.getElementById(id);
    const row = el?.closest('.bacteria-row');
    if (!el) return;
    const isOpen = el.classList.toggle('open');
    const arrow  = row?.querySelector('.expand-arrow');
    if (arrow) arrow.textContent = isOpen ? '↓' : '›';
}

// ── Plant diversity helper ─────────────────────────
function renderPlantDiversity(plants, count, target = 30) {
    const pct   = Math.min(100, Math.round((count / target) * 100));
    const color = pct >= 80 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444';

    const tags = plants.map(p =>
        `<span class="plant-tag">${p}</span>`
    ).join('');

    return `
        <div class="plant-diversity-section">
            <div class="plant-header">
                <span>🌱 Plant Diversity</span>
                <span style="color:${color};font-weight:600">
                    ${count} plants
                </span>
            </div>
            <div class="gut-bar-bg">
                <div class="gut-bar-fill"
                     style="width:${pct}%;background:${color}">
                </div>
            </div>
            <div class="plant-target-label">
                Target: 30 different plants per week
            </div>
            <div class="plant-tags">${tags}</div>
        </div>
    `;
}

// ── DAILY SCORECARD ────────────────────────────────
function renderDailyScorecard(container, data) {
    const score      = data.daily_gut_score || 0;
    const scoreColor = gutScoreColor(score);
    const scoreEmoji = gutScoreEmoji(score);

    container.innerHTML = `

        <!-- Overall Score -->
        <div class="gut-overall-score"
             style="border-color:${scoreColor}">
            <div class="gut-score-circle"
                 style="background:${scoreColor}">
                <span class="gut-score-num">${score}</span>
                <span class="gut-score-label">/ 10</span>
            </div>
            <div class="gut-score-info">
                <div class="gut-score-title">
                    ${scoreEmoji} Daily Gut Score
                </div>
                <div class="gut-score-notes">
                    ${data.meal_count} meals ·
                    ${data.plant_count} plants ·
                    FODMAP:
                    <span style="color:${fodmapColor(data.fodmap_worst)}">
                        ${(data.fodmap_worst||'low').toUpperCase()}
                    </span>
                </div>
            </div>
        </div>

        <!-- 4 Score Tiles -->
        <div class="gut-scores-grid">
            <div class="gut-score-tile">
                <span class="gut-tile-label">🌱 Prebiotic</span>
                <span class="gut-tile-value"
                      style="color:${gutScoreColor(data.avg_prebiotic)}">
                    ${data.avg_prebiotic}/10
                </span>
                ${scoreBar(data.avg_prebiotic)}
            </div>
            <div class="gut-score-tile">
                <span class="gut-tile-label">🔥 Anti-Inflam</span>
                <span class="gut-tile-value"
                      style="color:${gutScoreColor(data.avg_antiinflam)}">
                    ${data.avg_antiinflam}/10
                </span>
                ${scoreBar(data.avg_antiinflam)}
            </div>
            <div class="gut-score-tile">
                <span class="gut-tile-label">🦠 Probiotic</span>
                <span class="gut-tile-value"
                      style="color:${data.probiotic_meals > 0
                                     ? '#22c55e' : '#ef4444'}">
                    ${data.probiotic_meals > 0 ? '✅ Yes' : '❌ None'}
                </span>
            </div>
            <div class="gut-score-tile">
                <span class="gut-tile-label">🌿 FODMAP</span>
                <span class="gut-tile-value"
                      style="color:${fodmapColor(data.fodmap_worst)}">
                    ${(data.fodmap_worst||'low').toUpperCase()}
                </span>
            </div>
        </div>

        <!-- Bacteria Fed -->
        <div class="gut-section">
            <div class="gut-section-title">
                🦠 Bacteria Nourished
                <span class="gut-section-hint">tap to expand</span>
            </div>
            ${renderBacteriaFed(data.bacteria_fed || {})}
        </div>

        <!-- Bacteria Harmed -->
        <div class="gut-section">
            <div class="gut-section-title">
                ⚠️ Bacteria Harmed
                <span class="gut-section-hint">tap to expand</span>
            </div>
            ${renderBacteriaHarmed(data.bacteria_harmed || {})}
        </div>

        <!-- Plant Diversity -->
        <div class="gut-section">
            ${renderPlantDiversity(
                data.plant_diversity || [],
                data.plant_count     || 0,
                30
            )}
        </div>
    `;
}


// ── WEEKLY SCORECARD ───────────────────────────────
function renderWeeklyScorecard(container, data) {
    const avg        = data.avg_gut_score || 0;
    const scoreColor = gutScoreColor(avg);
    const dayNames   = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const dailyCards = data.daily_scorecards || [];

    // Day bars
    const dayBars = dailyCards.map((day, i) => {
        const score = day.daily_gut_score || 0;
        const pct   = Math.min(100, (score / 10) * 100);
        const color = score > 0 ? gutScoreColor(score) : '#374151';
        const today = new Date().toLocaleDateString('en-CA');
        const isToday = day.date === today;

        return `
            <div class="day-bar-col
                 ${isToday ? 'day-bar-today' : ''}">
                <div class="day-bar-score"
                     style="color:${color}">
                    ${score > 0 ? score : '—'}
                </div>
                <div class="day-bar-track">
                    <div class="day-bar-fill"
                         style="height:${pct}%;
                                background:${color}">
                    </div>
                </div>
                <div class="day-bar-label">${dayNames[i]}</div>
            </div>`;
    }).join('');

    // Bacteria league
    const bacteriaEntries = Object.entries(data.bacteria_fed || {})
        .sort((a, b) => b[1].count - a[1].count);

    const bacteriaRows = bacteriaEntries.map(([name, d], i) => {
        const medal = ['🥇','🥈','🥉'][i] || '';
        const pct   = Math.min(100, (d.count / 14) * 100);
        return `
            <div class="bacteria-league-row">
                <span class="league-medal">${medal}</span>
                <span class="league-name">${name}</span>
                <span class="league-count">${d.count}x</span>
                <div class="league-bar-bg">
                    <div class="league-bar-fill"
                         style="width:${pct}%;
                                background:${gutScoreColor(d.avg_strength)}">
                    </div>
                </div>
            </div>`;
    }).join('');

    container.innerHTML = `

        <!-- Weekly Score -->
        <div class="gut-overall-score"
             style="border-color:${scoreColor}">
            <div class="gut-score-circle"
                 style="background:${scoreColor}">
                <span class="gut-score-num">${avg}</span>
                <span class="gut-score-label">/ 10</span>
            </div>
            <div class="gut-score-info">
                <div class="gut-score-title">
                    ${gutScoreEmoji(avg)} Weekly Avg
                </div>
                <div class="gut-score-notes">
                    ${data.total_meals || 0} meals ·
                    ${data.plant_count || 0} unique plants
                </div>
                ${data.best_day ? `
                    <div class="gut-score-notes">
                        🏆 Best: ${data.best_day_score}/10 ·
                        📉 Worst: ${data.worst_day_score}/10
                    </div>` : ''}
            </div>
        </div>

        <!-- Day Bars -->
        <div class="gut-section">
            <div class="gut-section-title">📊 Daily Scores</div>
            <div class="day-bars-row">${dayBars}</div>
        </div>

        <!-- Bacteria League -->
        <div class="gut-section">
            <div class="gut-section-title">
                🦠 Bacteria League
            </div>
            ${bacteriaRows ||
              '<p class="hint">No data this week yet.</p>'}
        </div>

        <!-- Plant Diversity -->
        <div class="gut-section">
            ${renderPlantDiversity(
                data.plant_diversity || [],
                data.plant_count     || 0,
                30
            )}
        </div>

        <!-- Bacteria Harmed -->
        ${Object.keys(data.bacteria_harmed || {}).length ? `
            <div class="gut-section">
                <div class="gut-section-title">⚠️ Bacteria Harmed</div>
                ${renderBacteriaHarmed(data.bacteria_harmed)}
            </div>` : ''}
    `;
}

// ── MONTHLY SCORECARD ──────────────────────────────
function renderMonthlyScorecard(container, data) {
    const avg        = data.avg_gut_score || 0;
    const scoreColor = gutScoreColor(avg);
    const monthNames = ['Jan','Feb','Mar','Apr','May','Jun',
                        'Jul','Aug','Sep','Oct','Nov','Dec'];
    const monthLabel = `${monthNames[(data.month||1)-1]} ${data.year}`;

    // Top foods
    const topFoodsHtml = (data.top_foods || [])
        .slice(0, 5)
        .map(([name, count], i) => `
            <div class="top-food-row">
                <span class="top-food-rank">${i+1}</span>
                <span class="top-food-name">${name}</span>
                <span class="top-food-count">${count}x</span>
            </div>`).join('');

    // Bacteria this month
    const bacteriaHtml = Object.entries(data.bacteria_fed || {})
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 8)
        .map(([name, d]) => `
            <div class="bacteria-league-row">
                <span class="league-name">${name}</span>
                <span class="league-count">${d.count}x</span>
                <div class="league-bar-bg">
                    <div class="league-bar-fill"
                         style="width:${Math.min(100,(d.count/20)*100)}%;
                                background:${gutScoreColor(d.avg_strength)}">
                    </div>
                </div>
            </div>`).join('');

    container.innerHTML = `

        <!-- Monthly Score -->
        <div class="gut-overall-score"
             style="border-color:${scoreColor}">
            <div class="gut-score-circle"
                 style="background:${scoreColor}">
                <span class="gut-score-num">${avg}</span>
                <span class="gut-score-label">/ 10</span>
            </div>
            <div class="gut-score-info">
                <div class="gut-score-title">
                    ${gutScoreEmoji(avg)} ${monthLabel}
                </div>
                <div class="gut-score-notes">
                    ${data.total_meals || 0} meals ·
                    ${data.plant_count || 0} plants ·
                    ${data.fried_meals || 0} fried
                    ${(data.fried_meals || 0) > 5
                        ? '⚠️' : '✅'}
                </div>
            </div>
        </div>

        <!-- Bacteria This Month -->
        <div class="gut-section">
            <div class="gut-section-title">
                🦠 Bacteria Fed This Month
            </div>
            ${bacteriaHtml ||
              '<p class="hint">No data yet.</p>'}
        </div>

        <!-- Top Foods -->
        <div class="gut-section">
            <div class="gut-section-title">
                🥗 Most Eaten Foods
            </div>
            ${topFoodsHtml ||
              '<p class="hint">No meals logged yet.</p>'}
        </div>

        <!-- Plant Diversity -->
        <div class="gut-section">
            ${renderPlantDiversity(
                data.plant_diversity || [],
                data.plant_count     || 0,
                120
            )}
        </div>

        <!-- Bacteria Harmed -->
        ${Object.keys(data.bacteria_harmed || {}).length ? `
            <div class="gut-section">
                <div class="gut-section-title">
                    ⚠️ Bacteria Harmed
                </div>
                ${renderBacteriaHarmed(data.bacteria_harmed)}
            </div>` : ''}
    `;
}