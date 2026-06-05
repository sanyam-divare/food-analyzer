// ══════════════════════════════════════════════════
// gut_app.js  —  Gut Health Tracker (Persona 2)
// Loaded dynamically when gut mode is selected.
// Reuses shared camera/voice from index.html.
// ══════════════════════════════════════════════════

// ── State ─────────────────────────────────────────
let gutCurrentResults = null;
let gutMealTimestamp  = null;
let gutPatientId      = localStorage.getItem('gutPatientId') || 'guest';
let gutScorecardView  = 'daily';

// ── Init ──────────────────────────────────────────
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

        <!-- Gut Results injected here after analysis -->
        <div id="gut-results" style="display:none"></div>

        <!-- Scorecard -->
        <div class="card" style="margin-top:16px">
            <div class="gut-scorecard-header">
                <h2>📊 Gut Scorecard</h2>
                <div class="scorecard-tabs">
                    <button class="scorecard-tab active"
                            onclick="switchScorecardView('daily',this)">
                        Daily
                    </button>
                    <button class="scorecard-tab"
                            onclick="switchScorecardView('weekly',this)">
                        Weekly
                    </button>
                    <button class="scorecard-tab"
                            onclick="switchScorecardView('monthly',this)">
                        Monthly
                    </button>
                </div>
            </div>
            <div id="gut-scorecard"></div>
        </div>

        <!-- Gut Meal History -->
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

// ── Analyze photo (uses shared currentImageBase64) ─
async function gutAnalyzePhoto() {
    if (!currentImageBase64) {
        showError('Please take or upload a photo first!');
        return;
    }

    document.getElementById('gut-loading').style.display    = 'block';
    document.getElementById('gut-results').style.display    = 'none';
    document.getElementById('gut-analyze-btn').style.display = 'none';

    try {
        const response = await fetch('/gut/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image:        currentImageBase64,
                mime_type:    currentMimeType,
                provider:     document.getElementById('provider-select')?.value || 'claude',
                timezone:     getUserTimezone(),
                patient_id:   gutPatientId,
                image_width:  currentImageWidth,
                image_height: currentImageHeight
            })
        });

        const data = await response.json();

        if (data.error) {
            showError('Error: ' + data.error);
            document.getElementById('gut-analyze-btn').style.display = 'block';
            return;
        }

        gutCurrentResults = data;
        gutMealTimestamp  = data.timestamp;
        renderGutResults(data);

    } catch (err) {
        showError('Analysis failed: ' + err.message);
        document.getElementById('gut-analyze-btn').style.display = 'block';
    } finally {
        document.getElementById('gut-loading').style.display = 'none';
    }
}

// ── Analyze voice / text ──────────────────────────
async function gutAnalyzeVoice(text) {
    if (!text) {
        showError('Please speak or type your meal first.');
        return;
    }

    // Hide both voice buttons, show gut loading
    const hVoice = document.getElementById('analyze-voice-btn');
    const gVoice = document.getElementById('gut-analyze-voice-btn');
    if (hVoice) hVoice.style.display = 'none';
    if (gVoice) gVoice.style.display = 'none';

    document.getElementById('gut-loading').style.display = 'block';
    document.getElementById('gut-results').style.display = 'none';

    try {
        const response = await fetch('/gut/analyze-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text:       text,
                provider:   document.getElementById('provider-select')?.value || 'claude',
                timezone:   getUserTimezone(),
                patient_id: gutPatientId
            })
        });

        const data = await response.json();

        if (data.error) {
            showError('Error: ' + data.error);
            if (gVoice) gVoice.style.display = 'block';
            return;
        }

        gutCurrentResults = data;
        gutMealTimestamp  = data.timestamp;
        renderGutResults(data);

    } catch (err) {
        showError('Analysis failed: ' + err.message);
        if (gVoice) gVoice.style.display = 'block';
    } finally {
        document.getElementById('gut-loading').style.display = 'none';
    }
}

// ── Render gut results ────────────────────────────
function renderGutResults(data) {
    const foods        = data.foods || [];
    const score        = data.overall_gut_score || 0;
    const notes        = data.overall_gut_notes || '';
    const scoreColor   = score >= 7 ? '#22c55e' : score >= 5 ? '#f59e0b' : '#ef4444';
    const scoreEmoji   = score >= 7 ? '✅' : score >= 5 ? '⚠️' : '❌';

    const foodRows = foods.map(f => {
        const fodmapColor = f.fodmap === 'high'   ? '#ef4444'
                          : f.fodmap === 'medium' ? '#f59e0b' : '#22c55e';

        const bacteriaFed = (f.bacteria_fed || []).map(b => {
            const name     = typeof b === 'object' ? b.name           : b;
            const strength = typeof b === 'object' ? b.impact_strength : '';
            const mech     = typeof b === 'object' ? b.mechanism       : '';
            return `
                <div class="bacteria-item bacteria-positive">
                    <span class="bacteria-name">✅ ${name}</span>
                    ${strength
                        ? `<span class="bacteria-strength">${strength}/10</span>` : ''}
                    ${mech
                        ? `<div class="bacteria-mech">${mech}</div>` : ''}
                </div>`;
        }).join('');

        const bacteriaHarmed = (f.bacteria_harmed || []).map(b => {
            const name = typeof b === 'object' ? b.name : b;
            return `
                <div class="bacteria-item bacteria-negative">
                    <span class="bacteria-name">❌ ${name}</span>
                </div>`;
        }).join('');

        const fibres = (f.prebiotic_fibres || []).length
            ? `<div class="fibre-tags">
                ${f.prebiotic_fibres.map(fib =>
                    `<span class="fibre-tag">${fib}</span>`).join('')}
               </div>` : '';

        return `
            <div class="gut-food-card">
                <div class="gut-food-header">
                    <div class="gut-food-name">${f.name}</div>
                    <div class="gut-food-grams">${f.estimated_grams}g</div>
                </div>
                <div class="gut-scores-row">
                    <div class="gut-score-pill">
                        🌱 Prebiotic:
                        <strong>${f.prebiotic_score || 0}/10</strong>
                    </div>
                    <div class="gut-score-pill">
                        🔥 Anti-inflam:
                        <strong>${f.anti_inflammatory_score || 0}/10</strong>
                    </div>
                    <div class="gut-score-pill"
                         style="color:${fodmapColor}">
                        FODMAP:
                        <strong>${(f.fodmap || 'low').toUpperCase()}</strong>
                    </div>
                    ${f.probiotic
                        ? `<div class="gut-score-pill probiotic-badge">
                               🦠 Probiotic
                           </div>` : ''}
                </div>
                ${fibres}
                ${bacteriaFed || bacteriaHarmed ? `
                    <div class="bacteria-section">
                        ${bacteriaFed
                            ? `<div class="bacteria-group">${bacteriaFed}</div>` : ''}
                        ${bacteriaHarmed
                            ? `<div class="bacteria-group">${bacteriaHarmed}</div>` : ''}
                    </div>` : ''}
                ${f.gut_notes
                    ? `<div class="gut-food-notes">💬 ${f.gut_notes}</div>` : ''}
            </div>`;
    }).join('');

    const html = `
        <div class="card">
            <h2>🦠 Gut Impact Results</h2>
            <p class="meal-desc">${data.meal_description || ''}</p>

            <div class="gut-overall-score"
                 style="border-color:${scoreColor}">
                <div class="gut-score-circle"
                     style="background:${scoreColor}">
                    <span class="gut-score-num">${score}</span>
                    <span class="gut-score-label">/ 10</span>
                </div>
                <div class="gut-score-info">
                    <div class="gut-score-title">
                        ${scoreEmoji} Overall Gut Score
                    </div>
                    <div class="gut-score-notes">${notes}</div>
                </div>
            </div>

            <div class="gut-disclaimer">
                ⚠️ AI-powered estimates — validate with your practitioner
            </div>

            <div class="section-label">🥗 Food Breakdown</div>
            ${foodRows}

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
        </div>`;

    const el    = document.getElementById('gut-results');
    el.innerHTML = html;
    el.style.display = 'block';
    el.scrollIntoView({ behavior: 'smooth' });
}

// ── Confirm / Retake ──────────────────────────────
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
            alert('Failed to save: ' + result.error); return;
        }

        // Reset state
        gutCurrentResults = null;
        document.getElementById('gut-results').style.display    = 'none';
        document.getElementById('gut-analyze-btn').style.display = 'none';

        // Reset shared camera
        const photoPreview  = document.getElementById('photo-preview');
        const placeholder   = document.getElementById('camera-placeholder');
        if (photoPreview) photoPreview.style.display  = 'none';
        if (placeholder)  placeholder.style.display   = 'block';

        // Hide all voice/analyze buttons
        hideAllAnalyzeButtons();

        // Reset shared voice state (defined in app.js)
        voiceText = '';
        const vt = document.getElementById('voice-text');
        if (vt) vt.textContent = '';

        loadGutScorecard();
        loadGutHistory();
        window.scrollTo({ top: 0, behavior: 'smooth' });

        // Show brief success message
        showMessage('✓ Gut meal saved!');
        setTimeout(() => clearError(), 2000);

    } catch (err) {
        alert('Save failed: ' + err.message);
    }
}

function gutRejectResults() {
    gutCurrentResults = null;
    document.getElementById('gut-results').style.display    = 'none';
    document.getElementById('gut-analyze-btn').style.display = 'none';

    // Reset shared camera
    const photoPreview = document.getElementById('photo-preview');
    const placeholder  = document.getElementById('camera-placeholder');
    if (photoPreview) photoPreview.style.display = 'none';
    if (placeholder)  placeholder.style.display  = 'block';

    hideAllAnalyzeButtons();

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Gut History ───────────────────────────────────
async function loadGutHistory() {
    const container = document.getElementById('gut-history-list');
    if (!container) return;

    try {
        const res  = await fetch(`/gut/history?patient_id=${gutPatientId}`);
        const data = await res.json();

        if (!data.length) {
            container.innerHTML = '<p class="hint">No gut meals logged yet.</p>';
            return;
        }

        container.innerHTML = [...data].reverse().map(meal => {
            const s     = meal.overall_gut_score || 0;
            const color = s >= 7 ? '#22c55e' : s >= 5 ? '#f59e0b' : '#ef4444';
            const foods = (meal.foods || []).map(f => f.name).join(' · ');
            return `
                <div class="history-item">
                    <div class="history-date">📅 ${meal.timestamp || ''}</div>
                    <div class="history-desc">
                        ${meal.meal_description || ''}
                    </div>
                    <div class="history-foods">${foods}</div>
                    <div class="history-meta">
                        <span style="color:${color};font-weight:600">
                            🦠 Gut Score: ${s}/10
                        </span>
                    </div>
                </div>`;
        }).join('');

    } catch (err) {
        container.innerHTML = '<p class="hint">Could not load gut history.</p>';
    }
}

// ── Scorecard loader ──────────────────────────────
async function loadGutScorecard() {
    const container = document.getElementById('gut-scorecard');
    if (!container) return;

    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <p>Loading scorecard...</p>
        </div>`;

    try {
        const today = new Date().toLocaleDateString('en-CA');
        let url = '';

        if (gutScorecardView === 'daily') {
            url = `/gut/scorecard/daily?patient_id=${gutPatientId}&date=${today}`;
        } else if (gutScorecardView === 'weekly') {
            const now    = new Date();
            const monday = new Date(now);
            monday.setDate(now.getDate() - now.getDay() + 1);
            const weekStart = monday.toLocaleDateString('en-CA');
            url = `/gut/scorecard/weekly?patient_id=${gutPatientId}&week_start=${weekStart}`;
        } else {
            const now = new Date();
            url = `/gut/scorecard/monthly?patient_id=${gutPatientId}&year=${now.getFullYear()}&month=${now.getMonth()+1}`;
        }

        const res  = await fetch(url);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<p class="hint">Error: ${data.error}</p>`;
            return;
        }

        if (gutScorecardView === 'daily')   renderDailyScorecard(container, data);
        if (gutScorecardView === 'weekly')  renderWeeklyScorecard(container, data);
        if (gutScorecardView === 'monthly') renderMonthlyScorecard(container, data);

    } catch (err) {
        container.innerHTML =
            `<p class="hint">Could not load scorecard: ${err.message}</p>`;
    }
}

// ── Score helpers ─────────────────────────────────
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

// ── Bacteria renderers ────────────────────────────
function renderBacteriaFed(bacteria_fed) {
    const entries = Object.entries(bacteria_fed);
    if (!entries.length)
        return '<p class="hint">No bacteria fed recorded.</p>';

    entries.sort((a, b) => b[1].count - a[1].count);

    return entries.map(([name, data], idx) => {
        const color    = gutScoreColor(data.avg_strength);
        const pct      = Math.min(100, (data.avg_strength / 10) * 100);
        const expandId = `bact-fed-${idx}`;
        return `
            <div class="bacteria-row"
                 onclick="toggleExpand('${expandId}')">
                <div class="bacteria-row-header">
                    <span class="bacteria-row-name">✅ ${name}</span>
                    <div class="bacteria-row-right">
                        <span class="bacteria-row-count">${data.count}x</span>
                        <span class="bacteria-strength-badge"
                              style="color:${color}">
                            ${data.avg_strength}/10
                        </span>
                        <span class="expand-arrow">›</span>
                    </div>
                </div>
                <div class="bacteria-bar-row">
                    <div class="gut-bar-bg">
                        <div class="gut-bar-fill"
                             style="width:${pct}%;background:${color}">
                        </div>
                    </div>
                </div>
                <div class="bacteria-expand" id="${expandId}">
                    <div class="bacteria-row-foods">
                        🌿 via: ${data.from_foods.join(', ')}
                    </div>
                    ${data.mechanism
                        ? `<div class="bacteria-mech">
                               💬 ${data.mechanism}
                           </div>` : ''}
                </div>
            </div>`;
    }).join('');
}

function renderBacteriaHarmed(bacteria_harmed) {
    const entries = Object.entries(bacteria_harmed);
    if (!entries.length)
        return `<p class="hint" style="color:#22c55e">✅ None harmed</p>`;

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
                        <span class="bacteria-row-count">${data.count}x</span>
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

function toggleExpand(id) {
    const el    = document.getElementById(id);
    const row   = el?.closest('.bacteria-row');
    if (!el) return;
    const isOpen = el.classList.toggle('open');
    const arrow  = row?.querySelector('.expand-arrow');
    if (arrow) arrow.textContent = isOpen ? '↓' : '›';
}

function renderPlantDiversity(plants, count, target = 30) {
    const pct   = Math.min(100, Math.round((count / target) * 100));
    const color = pct >= 80 ? '#22c55e' : pct >= 50 ? '#f59e0b' : '#ef4444';
    const tags  = plants.map(p => `<span class="plant-tag">${p}</span>`).join('');
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
                Target: ${target} different plants per week
            </div>
            <div class="plant-tags">${tags}</div>
        </div>`;
}

// ── Daily scorecard ───────────────────────────────
function renderDailyScorecard(container, data) {
    const score      = data.daily_gut_score || 0;
    const scoreColor = gutScoreColor(score);
    const scoreEmoji = gutScoreEmoji(score);

    container.innerHTML = `
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

        <div class="gut-section">
            <div class="gut-section-title">
                🦠 Bacteria Nourished
                <span class="gut-section-hint">tap to expand</span>
            </div>
            ${renderBacteriaFed(data.bacteria_fed || {})}
        </div>

        <div class="gut-section">
            <div class="gut-section-title">
                ⚠️ Bacteria Harmed
                <span class="gut-section-hint">tap to expand</span>
            </div>
            ${renderBacteriaHarmed(data.bacteria_harmed || {})}
        </div>

        <div class="gut-section">
            ${renderPlantDiversity(
                data.plant_diversity || [],
                data.plant_count     || 0,
                30
            )}
        </div>`;
}

// ── Weekly scorecard ──────────────────────────────
function renderWeeklyScorecard(container, data) {
    const avg        = data.avg_gut_score || 0;
    const scoreColor = gutScoreColor(avg);
    const dayNames   = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const dailyCards = data.daily_scorecards || [];
    const today      = new Date().toLocaleDateString('en-CA');

    const dayBars = dailyCards.map((day, i) => {
        const s     = day.daily_gut_score || 0;
        const pct   = Math.min(100, (s / 10) * 100);
        const color = s > 0 ? gutScoreColor(s) : '#374151';
        return `
            <div class="day-bar-col
                 ${day.date === today ? 'day-bar-today' : ''}">
                <div class="day-bar-score" style="color:${color}">
                    ${s > 0 ? s : '—'}
                </div>
                <div class="day-bar-track">
                    <div class="day-bar-fill"
                         style="height:${pct}%;background:${color}">
                    </div>
                </div>
                <div class="day-bar-label">${dayNames[i]}</div>
            </div>`;
    }).join('');

    const bacteriaRows = Object.entries(data.bacteria_fed || {})
        .sort((a, b) => b[1].count - a[1].count)
        .map(([name, d], i) => {
            const medal = ['🥇','🥈','🥉'][i] || '';
            return `
                <div class="bacteria-league-row">
                    <span class="league-medal">${medal}</span>
                    <span class="league-name">${name}</span>
                    <span class="league-count">${d.count}x</span>
                    <div class="league-bar-bg">
                        <div class="league-bar-fill"
                             style="width:${Math.min(100,(d.count/14)*100)}%;
                                    background:${gutScoreColor(d.avg_strength)}">
                        </div>
                    </div>
                </div>`;
        }).join('');

    container.innerHTML = `
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
                    ${data.total_meals||0} meals ·
                    ${data.plant_count||0} unique plants
                </div>
                ${data.best_day ? `
                    <div class="gut-score-notes">
                        🏆 Best: ${data.best_day_score}/10 ·
                        📉 Worst: ${data.worst_day_score}/10
                    </div>` : ''}
            </div>
        </div>

        <div class="gut-section">
            <div class="gut-section-title">📊 Daily Scores</div>
            <div class="day-bars-row">${dayBars}</div>
        </div>

        <div class="gut-section">
            <div class="gut-section-title">🦠 Bacteria League</div>
            ${bacteriaRows ||
              '<p class="hint">No data this week yet.</p>'}
        </div>

        <div class="gut-section">
            ${renderPlantDiversity(
                data.plant_diversity || [],
                data.plant_count     || 0,
                30
            )}
        </div>

        ${Object.keys(data.bacteria_harmed || {}).length ? `
            <div class="gut-section">
                <div class="gut-section-title">⚠️ Bacteria Harmed</div>
                ${renderBacteriaHarmed(data.bacteria_harmed)}
            </div>` : ''}`;
}

// ── Monthly scorecard ─────────────────────────────
function renderMonthlyScorecard(container, data) {
    const avg        = data.avg_gut_score || 0;
    const scoreColor = gutScoreColor(avg);
    const monthNames = ['Jan','Feb','Mar','Apr','May','Jun',
                        'Jul','Aug','Sep','Oct','Nov','Dec'];
    const monthLabel = `${monthNames[(data.month||1)-1]} ${data.year}`;

    const topFoodsHtml = (data.top_foods || []).slice(0, 5)
        .map(([name, count], i) => `
            <div class="top-food-row">
                <span class="top-food-rank">${i+1}</span>
                <span class="top-food-name">${name}</span>
                <span class="top-food-count">${count}x</span>
            </div>`).join('');

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
                    ${data.total_meals||0} meals ·
                    ${data.plant_count||0} plants ·
                    ${data.fried_meals||0} fried
                    ${(data.fried_meals||0) > 5 ? '⚠️' : '✅'}
                </div>
            </div>
        </div>

        <div class="gut-section">
            <div class="gut-section-title">
                🦠 Bacteria Fed This Month
            </div>
            ${bacteriaHtml || '<p class="hint">No data yet.</p>'}
        </div>

        <div class="gut-section">
            <div class="gut-section-title">🥗 Most Eaten Foods</div>
            ${topFoodsHtml || '<p class="hint">No meals logged yet.</p>'}
        </div>

        <div class="gut-section">
            ${renderPlantDiversity(
                data.plant_diversity || [],
                data.plant_count     || 0,
                120
            )}
        </div>

        ${Object.keys(data.bacteria_harmed || {}).length ? `
            <div class="gut-section">
                <div class="gut-section-title">⚠️ Bacteria Harmed</div>
                ${renderBacteriaHarmed(data.bacteria_harmed)}
            </div>` : ''}`;
}
