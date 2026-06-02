// ── State ───────────────────────────────────────
// ── 1. DATE NAV STATE (add near top with other state variables) ─────────────
let historyDateOffset = 0; // 0 = today, -1 = yesterday, etc.
// Add these global variables near the top of app.js
// ── Extra globals for meal confirmation ──────────
let currentMealTimestamp = null;
let currentCuisineType = null;
let currentGutScore = 0;
let currentGutNotes = '';

// ── Timezone helper ──────────────────────────────
function getUserTimezone() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

// ── Format timestamp in user's local time ────────
function formatLocalTime(timestampStr) {
    if (!timestampStr) return '';
    try {
        const date = new Date(timestampStr.replace(' ', 'T'));
        return date.toLocaleString(undefined, {
            year:   'numeric',
            month:  '2-digit',
            day:    '2-digit',
            hour:   '2-digit',
            minute: '2-digit',
            hour12: true
        });
    } catch (e) {
        return timestampStr;
    }
}

// In showResults() function, add these lines:
function showResults(data) {
    clearError();

    // Store for confirmation later
    currentMealTimestamp = data.timestamp || null;
    currentCuisineType = data.cuisine_type || '';
    currentGutScore = data.overall_gut_health_score || 0;
    currentGutNotes = data.overall_gut_notes || '';

    // ... rest of your existing showResults code
}

function getHistoryDate(offset = 0) {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    // 'en-CA' gives YYYY-MM-DD format using the USER'S local timezone
    return d.toLocaleDateString('en-CA');  // no timeZone = browser
    // return d.toISOString().slice(0, 10);
}

function shiftHistoryDate(delta) {
    historyDateOffset += delta;
    // Don't allow future dates
    if (historyDateOffset > 0) { historyDateOffset = 0; }
    document.getElementById('date-nav-next').disabled = historyDateOffset >= 0;
    loadHistory();
}

function refreshHistory() {
    const btn = document.querySelector('.date-nav-refresh');
    if (btn) { btn.classList.add('spinning'); }
    loadHistory().finally(() => {
        if (btn) btn.classList.remove('spinning');
    });
}

function getUserTimezone() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
    // Returns e.g. "Australia/Melbourne", "America/New_York", "Asia/Kolkata"
}

function updateDateNavLabel() {
    const labelEl = document.getElementById('history-date-label');
    const subEl   = document.getElementById('history-date-sub');
    const nextBtn = document.getElementById('date-nav-next');
    if (!labelEl) return;

    if (historyDateOffset === 0) {
        labelEl.textContent = 'Today';
    } else if (historyDateOffset === -1) {
        labelEl.textContent = 'Yesterday';
    } else {
        const d = new Date();
        d.setDate(d.getDate() + historyDateOffset);
        labelEl.textContent = d.toLocaleDateString(undefined, {
            weekday: 'long'  // no timeZone = browser local ✅
        });
    }

    const dateStr = getHistoryDate(historyDateOffset);
    if (subEl) subEl.textContent = dateStr;
    if (nextBtn) nextBtn.disabled = historyDateOffset >= 0;
}
let currentImageBase64 = null;
let currentMimeType = 'image/jpeg';
let currentImageWidth = 0;
let currentImageHeight = 0;
// Safeguards for uploads to avoid browser OOM/crashes
const MAX_CLIENT_FILE_BYTES = 8 * 1024 * 1024; // 8 MB
const MAX_CLIENT_DIMENSION = { w: 4000, h: 3000 }; // refuse extremely large images
let voiceRecognition = null;
let isRecording = false;
let voiceText = '';
let currentResults = [];

function showError(message) {
    const errorBanner = document.getElementById('error-message');
    errorBanner.textContent = message;
    errorBanner.style.display = 'block';
    errorBanner.style.background = '#fee2e2';
    errorBanner.style.color = '#991b1b';
    errorBanner.style.borderColor = '#fca5a5';
}

function showMessage(message) {
    const errorBanner = document.getElementById('error-message');
    errorBanner.textContent = message;
    errorBanner.style.display = 'block';
    errorBanner.style.background = '#ecfdf5';
    errorBanner.style.color = '#166534';
    errorBanner.style.borderColor = '#a7f3d0';
}

function clearError() {
    const errorBanner = document.getElementById('error-message');
    errorBanner.textContent = '';
    errorBanner.style.display = 'none';
    errorBanner.style.background = '';
    errorBanner.style.color = '';
    errorBanner.style.borderColor = '';
}

function calculateRowNutrition(row) {
    const g = row.grams || 0;
    const base = row.per100 || {};
    const caloriesPer100 = base.energy_kcal || base.calories || 0;
    const carbsPer100 = base.carbohydrates || base.carbs || 0;

    return {
        ...row,
        calories: Number((caloriesPer100 * g / 100).toFixed(1)),
        protein: Number(((base.protein || 0) * g / 100).toFixed(1)),
        carbs: Number((carbsPer100 * g / 100).toFixed(1)),
        fat: Number(((base.fat || 0) * g / 100).toFixed(1)),
        fibre: Number(((base.fibre || 0) * g / 100).toFixed(1)),
        sugars: Number(((base.sugars || 0) * g / 100).toFixed(1)),
        sodium: Number(((base.sodium || 0) * g / 100).toFixed(1)),
        calcium: Number(((base.calcium || 0) * g / 100).toFixed(1)),
        iron: Number(((base.iron || 0) * g / 100).toFixed(2)),
        magnesium: Number(((base.magnesium || 0) * g / 100).toFixed(1)),
        potassium: Number(((base.potassium || 0) * g / 100).toFixed(1)),
        zinc: Number(((base.zinc || 0) * g / 100).toFixed(2)),
        vitamin_a: Number(((base.vitamin_a || 0) * g / 100).toFixed(1)),
        vitamin_c: Number(((base.vitamin_c || 0) * g / 100).toFixed(1)),
        vitamin_d: Number(((base.vitamin_d || 0) * g / 100).toFixed(2)),
        vitamin_e: Number(((base.vitamin_e || 0) * g / 100).toFixed(2)),
        cholesterol: Number(((base.cholesterol || 0) * g / 100).toFixed(1))
    };
}

function handleResultEdit(index, field, value) {
    if (!currentResults[index]) return;
    if (field === 'grams') {
        const grams = Number(value);
        currentResults[index].grams = isNaN(grams) ? 0 : grams;
        currentResults[index] = calculateRowNutrition(currentResults[index]);
    } else if (field === 'name') {
        currentResults[index].name = value;
    }
    // DON'T call renderResultRows() here — it destroys the input!
    // Instead just update the calculated cells + totals
    updateRowCells(index);
    refreshTotals();
}

// New function — updates only the number cells, not the inputs
function updateRowCells(index) {
    const f = currentResults[index];
    const row = document.querySelector(`#foods-list tr:nth-child(${index + 1})`);
    if (!row) return;

    const cells = row.querySelectorAll('td');
    // cells[0]=name input, cells[1]=amount input, then the numbers:
    if (cells[2]) cells[2].textContent = Math.round(f.calories);
    if (cells[3]) cells[3].textContent = f.protein.toFixed(1) + 'g';
    if (cells[4]) cells[4].textContent = f.carbs.toFixed(1) + 'g';
    if (cells[5]) cells[5].textContent = f.sugars.toFixed(1) + 'g';
    if (cells[6]) cells[6].textContent = f.fat.toFixed(1) + 'g';
    if (cells[7]) cells[7].textContent = f.fibre.toFixed(1) + 'g';

    // Update micro table row too
    const microRow = document.querySelector(`#micro-list tr:nth-child(${index + 1})`);
    if (microRow) {
        const m = microRow.querySelectorAll('td');
        if (m[1]) m[1].textContent = f.sodium.toFixed(1);
        if (m[2]) m[2].textContent = f.calcium.toFixed(1);
        if (m[3]) m[3].textContent = f.iron.toFixed(2);
        if (m[4]) m[4].textContent = f.magnesium.toFixed(1);
        if (m[5]) m[5].textContent = f.potassium.toFixed(1);
        if (m[6]) m[6].textContent = f.zinc.toFixed(2);
        if (m[7]) m[7].textContent = f.vitamin_a.toFixed(1);
        if (m[8]) m[8].textContent = f.vitamin_c.toFixed(1);
        if (m[9]) m[9].textContent = f.vitamin_d.toFixed(2);
        if (m[10]) m[10].textContent = f.vitamin_e.toFixed(2);
        if (m[11]) m[11].textContent = f.cholesterol.toFixed(1);
    }
}

function toggleRecCard(card) {
    const isOpen = card.classList.toggle('rec-open');
    card.querySelector('.rec-toggle').textContent = isOpen ? '−' : '+';
}

async function recalculateNutrition() {
    if (!currentResults.length) {
        showError('No nutrition results available to recalculate.');
        return;
    }

    clearError();
    showLoading(true);
    try {
        const response = await fetch('/recalculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ foods: currentResults.map(({ name, grams }) => ({ name, grams })) })
        });
        const data = await response.json();
        if (data.error) {
            showError('Error: ' + data.error);
            return;
        }
        if (!Array.isArray(data.foods)) {
            showError('Unexpected response from recalculation endpoint.');
            return;
        }
        currentResults = data.foods.map(f => {
            const grams = Number(f.grams) || 0;
            const per100 = f.per100 || {
                energy_kcal: grams ? (Number(f.calories) || 0) * 100 / grams : 0,
                protein: grams ? (Number(f.protein) || 0) * 100 / grams : 0,
                carbohydrates: grams ? (Number(f.carbs) || 0) * 100 / grams : 0,
                fat: grams ? (Number(f.fat) || 0) * 100 / grams : 0,
                fibre: grams ? (Number(f.fibre) || 0) * 100 / grams : 0,
                sugars: grams ? (Number(f.sugars) || 0) * 100 / grams : 0,
                sodium: grams ? (Number(f.sodium) || 0) * 100 / grams : 0,
                calcium: grams ? (Number(f.calcium) || 0) * 100 / grams : 0,
                iron: grams ? (Number(f.iron) || 0) * 100 / grams : 0,
                magnesium: grams ? (Number(f.magnesium) || 0) * 100 / grams : 0,
                potassium: grams ? (Number(f.potassium) || 0) * 100 / grams : 0,
                zinc: grams ? (Number(f.zinc) || 0) * 100 / grams : 0,
                vitamin_a: grams ? (Number(f.vitamin_a) || 0) * 100 / grams : 0,
                vitamin_c: grams ? (Number(f.vitamin_c) || 0) * 100 / grams : 0,
                vitamin_d: grams ? (Number(f.vitamin_d) || 0) * 100 / grams : 0,
                vitamin_e: grams ? (Number(f.vitamin_e) || 0) * 100 / grams : 0,
                cholesterol: grams ? (Number(f.cholesterol) || 0) * 100 / grams : 0
            };
            return calculateRowNutrition({ ...f, grams, per100 });
        });
        renderResultRows();
        showMessage('Nutrition recalculated locally using DB-based matching.');
    } catch (err) {
        showError('Recalculation failed: ' + err.message);
    } finally {
        showLoading(false);
    }
}

function removeFood(index) {
    currentResults.splice(index, 1);   // remove from array
    renderResultRows();                 // safe to re-render here (not typing)
}

async function addNewFood() {
    const nameInput = document.getElementById('new-food-name');
    const gramsInput = document.getElementById('new-food-grams');
    const name = nameInput.value.trim();
    const grams = Number(gramsInput.value) || 100;

    if (!name) {
        showError('Please enter a food name');
        return;
    }

    showLoading(true);
    try {
        // Use your existing /recalculate endpoint to look up the new food!
        const response = await fetch('/recalculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ foods: [{ name, grams }] })
        });
        const data = await response.json();

        if (data.foods && data.foods[0]) {
            const f = data.foods[0];
            const per100 = f.per100 || {};
            currentResults.push(calculateRowNutrition({ ...f, grams, per100 }));
            renderResultRows();
            nameInput.value = '';
            gramsInput.value = '100';

            if (!f.found_in_db) {
                showError(`"${name}" not found in database — added with zero values. Try a simpler name.`);
            } else {
                showMessage(`Added: ${f.matched || name}`);
            }
        }
    } catch (err) {
        showError('Failed to add food: ' + err.message);
    } finally {
        showLoading(false);
    }
}

function renderResultRows() {
    const foodsHtml = currentResults.map((f, index) => `
        <tr>
            <td>
                <input type="text" class="food-edit" value="${f.name}" data-index="${index}" data-field="name" />
                ${f.matched && f.matched !== f.name ?
                    `<div style="font-size:0.7rem;color:var(--gray-400)">Matched: ${f.matched}</div>` : ''}
                ${!f.found_in_db ? '<span class="not-in-db">~</span>' : ''}
            </td>
            <td><input type="number" min="0" class="amount-edit" value="${f.grams}" data-index="${index}" data-field="grams" /></td>
            <td class="kcal-cell">${Math.round(f.calories)}</td>
            <td>${f.protein.toFixed(1)}g</td>
            <td>${f.carbs.toFixed(1)}g</td>
            <td>${f.sugars.toFixed(1)}g</td>
            <td>${f.fat.toFixed(1)}g</td>
            <td>${f.fibre.toFixed(1)}g</td>
            <td><button class="remove-food-btn" data-index="${index}" title="Remove">✕</button></td>
        </tr>
    `).join('');

    const microHtml = currentResults.map(f => `
        <tr>
            <td>${f.name.length > 20 ? f.name.substring(0,20)+'…' : f.name}</td>
            <td>${f.sodium.toFixed(1)}</td>
            <td>${f.calcium.toFixed(1)}</td>
            <td>${f.iron.toFixed(2)}</td>
            <td>${f.magnesium.toFixed(1)}</td>
            <td>${f.potassium.toFixed(1)}</td>
            <td>${f.zinc.toFixed(2)}</td>
            <td>${f.vitamin_a.toFixed(1)}</td>
            <td>${f.vitamin_c.toFixed(1)}</td>
            <td>${f.vitamin_d.toFixed(2)}</td>
            <td>${f.vitamin_e.toFixed(2)}</td>
            <td>${f.cholesterol.toFixed(1)}</td>
        </tr>
    `).join('');

    document.getElementById('foods-list').innerHTML = foodsHtml;
    document.getElementById('micro-list').innerHTML = microHtml;

    document.querySelectorAll('.food-edit, .amount-edit').forEach(input => {
        input.addEventListener('input', (event) => {
            const idx = Number(event.target.dataset.index);
            const field = event.target.dataset.field;
            handleResultEdit(idx, field, event.target.value);
        });
    });

    // Wire up remove buttons
    document.querySelectorAll('.remove-food-btn').forEach(btn => {
        btn.addEventListener('click', (event) => {
            const idx = Number(event.target.dataset.index);
            removeFood(idx);
        });
    });

    // document.querySelectorAll('.food-edit, .amount-edit').forEach(input => {
    //     input.addEventListener('input', (event) => {
    //         const idx = Number(event.target.dataset.index);
    //         const field = event.target.dataset.field;
    //         handleResultEdit(idx, field, event.target.value);
    //     });
    // });

    refreshTotals();
}

// function confirmResults() {
//     showMessage('✓ Meal saved!');
//     setTimeout(() => {
//         resetApp();
//         // Scroll back to top
//         window.scrollTo({ top: 0, behavior: 'smooth' });
//         // Click the first tab (Analyze tab)
//         document.querySelector('.tab')?.click();
//     }, 1000);
// }

// function rejectResults() {
//     currentResults = [];
//     document.getElementById('results').style.display = 'none';
//     window.scrollTo({ top: 0, behavior: 'smooth' });
//     document.querySelector('.tab')?.click();
//     resetApp();
// }

async function confirmResults() {
    try {
        const mealData = {
            meal_description:         document.getElementById('meal-description').textContent,
            foods:                    currentResults,
            total_calories:           currentResults.reduce((sum, f) => sum + (f.calories || 0), 0),
            timestamp:                currentMealTimestamp,
            cuisine_type:             currentCuisineType,
            overall_gut_health_score: currentGutScore,
            overall_gut_notes:        currentGutNotes,
            timezone:                 getUserTimezone()   // ← add this
        };

        const response = await fetch('/confirm-meal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(mealData)
        });

        const result = await response.json();

        if (result.error) {
            showError('Failed to save: ' + result.error);
            return;
        }

        showMessage('✓ Meal saved to your history!');
        setTimeout(() => {
            resetApp();
            window.scrollTo({ top: 0, behavior: 'smooth' });
            document.querySelector('.tab')?.click();
        }, 1000);

    } catch (err) {
        showError('Failed to save meal: ' + err.message);
    }
}

function rejectResults() {
    // Just discard — nothing to undo since we no longer auto-save
    currentResults = [];
    document.getElementById('results').style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    document.querySelector('.tab')?.click();
    resetApp();
}


// function rejectResults() {
//     // User not happy — reset and let them retake
//     if (confirm('Discard these results and start over?')) {
//         currentResults = [];
//         resetApp();
//         showTab('camera');
//     }
// }

function refreshTotals() {
    let totals = {
        cal:0, protein:0, carbs:0, fat:0, fibre:0, sugars:0,
        sodium:0, calcium:0, iron:0, magnesium:0, potassium:0,
        zinc:0, vitamin_a:0, vitamin_c:0, vitamin_d:0, vitamin_e:0, cholesterol:0
    };

    currentResults.forEach(f => {
        totals.cal       += f.calories    || 0;
        totals.protein   += f.protein     || 0;
        totals.carbs     += f.carbs       || 0;
        totals.fat       += f.fat         || 0;
        totals.fibre     += f.fibre       || 0;
        totals.sugars    += f.sugars      || 0;
        totals.sodium    += f.sodium      || 0;
        totals.calcium   += f.calcium     || 0;
        totals.iron      += f.iron        || 0;
        totals.magnesium += f.magnesium   || 0;
        totals.potassium += f.potassium   || 0;
        totals.zinc      += f.zinc        || 0;
        totals.vitamin_a += f.vitamin_a   || 0;
        totals.vitamin_c += f.vitamin_c   || 0;
        totals.vitamin_d += f.vitamin_d   || 0;
        totals.vitamin_e += f.vitamin_e   || 0;
        totals.cholesterol += f.cholesterol || 0;
    });

    document.getElementById('summary-cal').textContent     = Math.round(totals.cal) + ' kcal';
    document.getElementById('summary-protein').textContent = totals.protein.toFixed(1) + 'g';
    document.getElementById('summary-carbs').textContent   = totals.carbs.toFixed(1) + 'g';
    document.getElementById('summary-fat').textContent     = totals.fat.toFixed(1) + 'g';

    document.getElementById('total-cal').textContent      = Math.round(totals.cal);
    document.getElementById('total-protein').textContent  = totals.protein.toFixed(1) + 'g';
    document.getElementById('total-carbs').textContent    = totals.carbs.toFixed(1) + 'g';
    document.getElementById('total-sugars').textContent   = totals.sugars.toFixed(1) + 'g';
    document.getElementById('total-fat').textContent      = totals.fat.toFixed(1) + 'g';
    document.getElementById('total-fibre').textContent    = totals.fibre.toFixed(1) + 'g';

    document.getElementById('total-sodium').textContent     = totals.sodium.toFixed(1);
    document.getElementById('total-calcium').textContent    = totals.calcium.toFixed(1);
    document.getElementById('total-iron').textContent       = totals.iron.toFixed(2);
    document.getElementById('total-magnesium').textContent  = totals.magnesium.toFixed(1);
    document.getElementById('total-potassium').textContent  = totals.potassium.toFixed(1);
    document.getElementById('total-zinc').textContent       = totals.zinc.toFixed(2);
    document.getElementById('total-vitamin-a').textContent  = totals.vitamin_a.toFixed(1);
    document.getElementById('total-vitamin-c').textContent  = totals.vitamin_c.toFixed(1);
    document.getElementById('total-vitamin-d').textContent  = totals.vitamin_d.toFixed(2);
    document.getElementById('total-vitamin-e').textContent  = totals.vitamin_e.toFixed(2);
    document.getElementById('total-cholesterol').textContent = totals.cholesterol.toFixed(1);
}

// // ── Tabs ────────────────────────────────────────
// function showTab(tab) {
//     document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
//     document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
//     document.getElementById(`tab-${tab}`).classList.add('active');
//     event.target.classList.add('active');
//     if (tab === 'history') loadHistory();
// }
// ── 5. UPDATE showTab() to reset date offset when switching to history ───────
// Replace existing showTab():
function showTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    event.target.classList.add('active');

    if (tab === 'history') {
        historyDateOffset = 0; // reset to today on each visit
        loadHistory();
    }
}
// ── Camera ──────────────────────────────────────
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment' }
        });
        const video = document.getElementById('camera-preview');
        video.srcObject = stream;
        video.style.display = 'block';
        document.getElementById('photo-preview').style.display = 'none';
        document.getElementById('camera-placeholder').style.display = 'none';
        document.getElementById('capture-btn').style.display = 'block';
        document.getElementById('analyze-btn').style.display = 'none';
        currentImageBase64 = null;
    } catch (err) {
        alert('Camera access denied. Please use Upload Photo instead.');
    }
}

function capturePhoto() {
    const video = document.getElementById('camera-preview');
    const canvas = document.getElementById('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    video.srcObject.getTracks().forEach(t => t.stop());
    video.style.display = 'none';

    const imageData = canvas.toDataURL('image/jpeg', 0.8);
    const preview = document.getElementById('photo-preview');
    preview.src = imageData;
    preview.style.display = 'block';
    currentImageBase64 = imageData.split(',')[1];
    currentMimeType = 'image/jpeg';
    currentImageWidth = canvas.width;
    currentImageHeight = canvas.height;

    // Disable OpenAI provider for image uploads (unsafe embed flow)
    const opt = document.querySelector('#provider-select option[value="openai"]');
    if (opt) {
        opt.disabled = true;
        const sel = document.getElementById('provider-select');
        if (sel.value === 'openai') {
            sel.value = 'gemini';
            showError('OpenAI vision via embed is disabled. Switched to Gemini for images.');
        }
    }

    document.getElementById('capture-btn').style.display = 'none';
    document.getElementById('analyze-btn').style.display = 'block';
}

function uploadPhoto() {
    document.getElementById('file-input').click();
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    currentMimeType = file.type || 'image/jpeg';

    // Quick safety checks
    if (file.size > MAX_CLIENT_FILE_BYTES) {
        // Warn but continue — we'll downscale below. If extremely large, abort.
        if (file.size > 20 * 1024 * 1024) {
            showError('Selected image is very large (>20MB). Please choose a smaller photo.');
            return;
        }
        showError('Large image selected. The app will downscale it to avoid browser crashes.');
    }

    // Use createImageBitmap when available to avoid creating huge data URLs up front
    const processBitmap = async (bitmap) => {
        try {
            const origW = bitmap.width, origH = bitmap.height;
            if (origW > MAX_CLIENT_DIMENSION.w || origH > MAX_CLIENT_DIMENSION.h) {
                showError('Very large image selected; attempting to downscale to 1200x900. If the browser becomes unresponsive, pick a smaller image.');
                // continue and attempt client-side downscale to avoid blocking the user
            }

            // Client-side downscale to a manageable preview size (match server target)
            const maxW = 1200, maxH = 900;
            const ratio = Math.min(maxW / origW, maxH / origH, 1);
            const tw = Math.max(1, Math.round(origW * ratio));
            const th = Math.max(1, Math.round(origH * ratio));

            const canvas = document.createElement('canvas');
            canvas.width = tw;
            canvas.height = th;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(bitmap, 0, 0, tw, th);

            // release bitmap memory
            if (bitmap.close) try { bitmap.close(); } catch (e) {}

            const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
            currentImageWidth = tw;
            currentImageHeight = th;
            document.getElementById('photo-preview').src = dataUrl;
            document.getElementById('photo-preview').style.display = 'block';
            document.getElementById('camera-preview').style.display = 'none';
            document.getElementById('camera-placeholder').style.display = 'none';
            currentImageBase64 = dataUrl.split(',')[1];
            document.getElementById('analyze-btn').style.display = 'block';
            // Disable OpenAI provider for image uploads (unsafe embed flow)
            const optImg = document.querySelector('#provider-select option[value="openai"]');
            if (optImg) {
                optImg.disabled = true;
                const selImg = document.getElementById('provider-select');
                if (selImg.value === 'openai') {
                    selImg.value = 'gemini';
                    showError('OpenAI vision via embed is disabled. Switched to Gemini for images.');
                }
            }
        } catch (err) {
            showError('Failed to process image: ' + err.message);
        }
    };

    if (window.createImageBitmap) {
        // createImageBitmap accepts a Blob directly
        createImageBitmap(file).then(processBitmap).catch(async (err) => {
            // fallback: read as DataURL but carefully
            try {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const imageData = e.target.result;
                    const img = new Image();
                    img.onload = async () => {
                        // reuse existing resize routine
                        try {
                            const smallBase64 = await resizeImageBase64(imageData.split(',')[1], currentMimeType, 1200, 900, 0.8);
                            document.getElementById('photo-preview').src = `data:${currentMimeType};base64,${smallBase64}`;
                            document.getElementById('photo-preview').style.display = 'block';
                            document.getElementById('camera-preview').style.display = 'none';
                            document.getElementById('camera-placeholder').style.display = 'none';
                            currentImageBase64 = smallBase64;
                            document.getElementById('analyze-btn').style.display = 'block';
                            // Disable OpenAI provider for image uploads (unsafe embed flow)
                            const optImg2 = document.querySelector('#provider-select option[value="openai"]');
                            if (optImg2) {
                                optImg2.disabled = true;
                                const selImg2 = document.getElementById('provider-select');
                                if (selImg2.value === 'openai') {
                                    selImg2.value = 'gemini';
                                    showError('OpenAI vision via embed is disabled. Switched to Gemini for images.');
                                }
                            }
                        } catch (e) {
                            showError('Image processing failed. Try a smaller image.');
                        }
                    };
                    img.onerror = () => showError('Could not load selected image.');
                    img.src = imageData;
                };
                reader.readAsDataURL(file);
            } catch (e) {
                showError('Could not read file: ' + e.message);
            }
        });
    } else {
        // Older browsers: fallback to FileReader path
        const reader = new FileReader();
        reader.onload = (e) => {
            const imageData = e.target.result;
            resizeImageBase64(imageData.split(',')[1], currentMimeType, 1200, 900, 0.8).then((smallBase64) => {
                document.getElementById('photo-preview').src = `data:${currentMimeType};base64,${smallBase64}`;
                document.getElementById('photo-preview').style.display = 'block';
                document.getElementById('camera-preview').style.display = 'none';
                document.getElementById('camera-placeholder').style.display = 'none';
                currentImageBase64 = smallBase64;
                document.getElementById('analyze-btn').style.display = 'block';
                // Disable OpenAI provider for image uploads (unsafe embed flow)
                const optImg3 = document.querySelector('#provider-select option[value="openai"]');
                if (optImg3) {
                    optImg3.disabled = true;
                    const selImg3 = document.getElementById('provider-select');
                    if (selImg3.value === 'openai') {
                        selImg3.value = 'gemini';
                        showError('OpenAI vision via embed is disabled. Switched to Gemini for images.');
                    }
                }
            }).catch(() => showError('Image processing failed. Try a smaller image.'));
        };
        reader.readAsDataURL(file);
    }
}

// Re-enable OpenAI option when resetting the app
function enableOpenAIOption() {
    const opt = document.querySelector('#provider-select option[value="openai"]');
    if (opt) opt.disabled = false;
}

function getSelectedProvider() {
    return document.getElementById('provider-select')?.value || 'gemini';
}

// ── Analyze Photo ────────────────────────────────
function resizeImageBase64(base64Data, mimeType = 'image/jpeg', maxW = 1200, maxH = 900, quality = 0.8) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            let w = img.width, h = img.height;
            const ratio = Math.min(maxW / w, maxH / h, 1);
            const tw = Math.max(1, Math.round(w * ratio));
            const th = Math.max(1, Math.round(h * ratio));
            const canvas = document.createElement('canvas');
            canvas.width = tw;
            canvas.height = th;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, tw, th);
            try {
                const dataUrl = canvas.toDataURL(mimeType, quality);
                resolve(dataUrl.split(',')[1]);
            } catch (e) {
                reject(e);
            }
        };
        img.onerror = (e) => reject(e);
        img.src = `data:${mimeType};base64,${base64Data}`;
    });
}

async function compressBase64ToLimit(base64Data, mimeType = 'image/jpeg', maxBytes = 140 * 1024) {
    // Try progressively reducing quality and resolution until under maxBytes
    let q = 0.8;
    let img = new Image();
    img.src = `data:${mimeType};base64,${base64Data}`;
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; });
    let w = img.width, h = img.height;
    let dataUrl = `data:${mimeType};base64,${base64Data}`;
    // quick check
    let bytes = Math.ceil((dataUrl.length - dataUrl.indexOf(',') - 1) * 3 / 4);
    if (bytes <= maxBytes) return { base64: base64Data, width: w, height: h, compressed: false };

    for (let attempt = 0; attempt < 6; attempt++) {
        const canvas = document.createElement('canvas');
        // progressively downscale by 90% per iteration after a couple quality reductions
        const scale = attempt >= 2 ? Math.pow(0.9, attempt - 1) : 1;
        canvas.width = Math.max(1, Math.round(w * scale));
        canvas.height = Math.max(1, Math.round(h * scale));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        try {
            const url = canvas.toDataURL(mimeType, q);
            const b64 = url.split(',')[1];
            const bbytes = Math.ceil(b64.length * 3 / 4);
            if (bbytes <= maxBytes) {
                return { base64: b64, width: canvas.width, height: canvas.height, compressed: true };
            }
            // reduce quality for next round
            q = Math.max(0.2, q - 0.15);
            // small delay to allow browser to breathe on heavy images
            await new Promise(r => setTimeout(r, 50));
        } catch (e) {
            // if toDataURL fails, break
            break;
        }
    }
    // last resort: return the last generated smaller image (if any), else original
    try {
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(w * 0.6));
        canvas.height = Math.max(1, Math.round(h * 0.6));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const url = canvas.toDataURL(mimeType, 0.5);
        const b64 = url.split(',')[1];
        return { base64: b64, width: canvas.width, height: canvas.height, compressed: true };
    } catch (e) {
        return { base64: base64Data, width: w, height: h, compressed: false };
    }
}

async function analyzePhoto() {
    if (!currentImageBase64) { showError('Please take or upload a photo first!'); return; }
    clearError();
    showLoading(true);
    document.getElementById('analyze-btn').style.display = 'none';
    document.getElementById('results').style.display = 'none';
    try {
        let sendBase64 = currentImageBase64;
        try {
            // First ensure image is at target 1200x900 max
            const resized = await resizeImageBase64(currentImageBase64, currentMimeType, 1200, 900, 0.8);
            // Then compress iteratively to a reasonable upload byte size
            const compressed = await compressBase64ToLimit(resized, currentMimeType, 140 * 1024);
            sendBase64 = compressed.base64;
            // update client-side dimensions if compression downscaled image
            if (compressed.width && compressed.height) {
                currentImageWidth = compressed.width;
                currentImageHeight = compressed.height;
            }
            if (compressed.compressed) showError('Image compressed client-side to reduce upload size.');
        } catch (e) {
            console.warn('Image resize/compress failed, falling back to original image:', e);
            sendBase64 = currentImageBase64;
        }

        // build body and estimate tokens (approx 1 token ≈ 4 chars)
        const bodyObj = { image: sendBase64, mime_type: currentMimeType, provider: getSelectedProvider(), image_width: currentImageWidth, image_height: currentImageHeight,timezone: getUserTimezone() };
        const bodyStr = JSON.stringify(bodyObj);
        const estimatedTokens = Math.ceil(bodyStr.length / 4);
        bodyObj.client_estimated_tokens = estimatedTokens;

        const response = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyObj)
        });
        const data = await response.json();
        if (data.error) { showError('Error: ' + data.error); }
        else { showResults(data); }
    } catch (err) {
        showError('Something went wrong: ' + err.message);
    } finally { showLoading(false); }
}

// ── Text ────────────────────────────────────────
function useTypedText() {
    const input = document.getElementById('manual-text-input');
    const text = input.value.trim();
    if (!text) {
        showError('Please type your meal description first.');
        return;
    }
    // Set voiceText same as if user had spoken it
    voiceText = text;
    document.getElementById('voice-text').textContent = text;
    document.getElementById('analyze-voice-btn').style.display = 'block';
    input.value = '';
}

// Allow pressing Enter in the text input
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('manual-text-input');
    if (input) {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') useTypedText();
        });
    }
});

// ── Voice ────────────────────────────────────────
function toggleVoice() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert('Voice not supported. Try Chrome or Samsung Browser.');
        return;
    }
    isRecording ? stopVoice() : startVoice();
}

function startVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    voiceRecognition = new SR();
    voiceRecognition.continuous = false;
    voiceRecognition.interimResults = true;
    voiceRecognition.lang = 'en-US';
    voiceRecognition.onresult = (e) => {
        const t = Array.from(e.results).map(r => r[0].transcript).join('');
        document.getElementById('voice-text').textContent = t;
        voiceText = t;
    };
    voiceRecognition.onend = () => {
        isRecording = false;
        const btn = document.getElementById('voice-btn');
        btn.textContent = '🎤 Tap to Speak';
        btn.classList.remove('recording');
        if (voiceText) document.getElementById('analyze-voice-btn').style.display = 'block';
    };
    voiceRecognition.onerror = (e) => {
        isRecording = false;
        document.getElementById('voice-btn').classList.remove('recording');
        alert('Voice error: ' + e.error);
    };
    voiceRecognition.start();
    isRecording = true;
    const btn = document.getElementById('voice-btn');
    btn.textContent = '⏹️ Stop Recording';
    btn.classList.add('recording');
}

function stopVoice() { if (voiceRecognition) voiceRecognition.stop(); }

async function analyzeVoice() {
    if (!voiceText) { showError('Please speak your meal description first.'); return; }
    clearError();
    showLoading(true);
    document.getElementById('analyze-voice-btn').style.display = 'none';
    document.getElementById('results').style.display = 'none';
    try {
        const response = await fetch('/analyze-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: voiceText, provider: getSelectedProvider(),timezone: getUserTimezone() })
        });
        const data = await response.json();
        if (data.error) { showError('Error: ' + data.error); }
        else { showResults(data); }
    } catch (err) {
        showError('Something went wrong: ' + err.message);
    } finally { showLoading(false); }
}

// ── Show Results ─────────────────────────────────
function showResults(data) {
    clearError();
    document.getElementById('meal-description').textContent = data.meal_description;
    // Populate debug log if provided by server
    try {
        const dbg = document.getElementById('debug-log');
        if (data.debug_log && Array.isArray(data.debug_log) && data.debug_log.length) {
            dbg.textContent = data.debug_log.join('\n');
            dbg.style.display = 'block';
        } else {
            dbg.textContent = '';
            dbg.style.display = 'none';
        }
    } catch (e) { /* ignore if debug element missing */ }

    currentResults = data.foods.map(f => {
        const grams = Number(f.grams) || 0;
        const per100 = {
            calories: grams ? (Number(f.calories) || 0) * 100 / grams : 0,
            protein: grams ? (Number(f.protein) || 0) * 100 / grams : 0,
            carbs: grams ? (Number(f.carbs) || 0) * 100 / grams : 0,
            fat: grams ? (Number(f.fat) || 0) * 100 / grams : 0,
            fibre: grams ? (Number(f.fibre) || 0) * 100 / grams : 0,
            sugars: grams ? (Number(f.sugars) || 0) * 100 / grams : 0,
            sodium: grams ? (Number(f.sodium) || 0) * 100 / grams : 0,
            calcium: grams ? (Number(f.calcium) || 0) * 100 / grams : 0,
            iron: grams ? (Number(f.iron) || 0) * 100 / grams : 0,
            magnesium: grams ? (Number(f.magnesium) || 0) * 100 / grams : 0,
            potassium: grams ? (Number(f.potassium) || 0) * 100 / grams : 0,
            zinc: grams ? (Number(f.zinc) || 0) * 100 / grams : 0,
            vitamin_a: grams ? (Number(f.vitamin_a) || 0) * 100 / grams : 0,
            vitamin_c: grams ? (Number(f.vitamin_c) || 0) * 100 / grams : 0,
            vitamin_d: grams ? (Number(f.vitamin_d) || 0) * 100 / grams : 0,
            vitamin_e: grams ? (Number(f.vitamin_e) || 0) * 100 / grams : 0,
            cholesterol: grams ? (Number(f.cholesterol) || 0) * 100 / grams : 0
        };
        return calculateRowNutrition({ ...f, grams, per100 });
    });

    renderResultRows();
    document.getElementById('results').style.display = 'block';
    document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

// ── History ──────────────────────────────────────
// async function loadHistory() {
//     try {
//         const response = await fetch('/history');
//         const data = await response.json();
//         const container = document.getElementById('history-list');
//         if (data.length === 0) {
//             container.innerHTML = '<p class="hint">No meals logged yet!</p>';
//             return;
//         }
//         container.innerHTML = data.reverse().map(meal => `
//             <div class="history-item">
//                 <div class="history-date">📅 ${meal.timestamp}</div>
//                 <div class="history-desc">${meal.meal_description}</div>
//                 <div class="history-foods">${meal.foods.map(f => `${f.name} (${f.grams}g)`).join(' · ')}</div>
//                 <div class="history-cal">🔥 ${meal.total_calories} kcal</div>
//             </div>
//         `).join('');
//     } catch (err) {
//         document.getElementById('history-list').innerHTML = '<p class="hint">Could not load history.</p>';
//     }
// }
// ── Replace loadHistory() in app.js with this ────────

// async function loadHistory() {
//     const container = document.getElementById('history-list');
//     container.innerHTML = '<p class="hint">Loading…</p>';
//     try {
//         // Load daily view (today)
//         const today = new Date().toISOString().slice(0, 10);
//         const [dailyRes, allRes] = await Promise.all([
//             fetch(`/history/daily?date=${today}`),
//             fetch('/history')
//         ]);
//         const daily = await dailyRes.json();
//         const all   = await allRes.json();

//         if (daily.error) {
//             container.innerHTML = `<p class="hint">Error: ${daily.error}</p>`;
//             return;
//         }

//         container.innerHTML = `
//             ${buildDailyGaps(daily)}
//             ${buildTimeline(daily)}
//             ${buildPastMeals(all, today)}
//         `;
//     } catch (e) {
//         container.innerHTML = `<p class="hint">Could not load history: ${e.message}</p>`;
//     }
// }
// ── Add to app.js ─────────────────────────────────────
// Call this inside loadHistory() after buildDailyGaps()
// e.g. container.innerHTML = buildFitnessPanel(fitness) + buildDailyGaps(daily) + ...

// ── 4. NEW buildRecCard() ────────────────────────────────────────────────────
// Type-aware card renderer. Handles: activity, timing, meal_timing, nutrient, reminder

const REC_TYPE_META = {
    activity:    { accent: 'rec-activity',    badge: 'Activity'    },
    timing:      { accent: 'rec-timing',      badge: 'Right Now'   },
    meal_timing: { accent: 'rec-meal-timing', badge: 'Meal Plan'   },
    nutrient:    { accent: 'rec-nutrient',    badge: 'Nutrition'   },
    reminder:    { accent: 'rec-reminder',    badge: 'Reminder'    },
    calorie:     { accent: 'rec-nutrient',    badge: 'Calories'    },
};

const PRIORITY_DOT = {
    high:   '<span class="rec-dot dot-high"></span>',
    medium: '<span class="rec-dot dot-medium"></span>',
    caution:'<span class="rec-dot dot-caution"></span>',
    low:    '<span class="rec-dot dot-low"></span>',
};
function buildRecCard(r) {
    const meta   = REC_TYPE_META[r.type] || REC_TYPE_META.nutrient;
    const dot    = PRIORITY_DOT[r.priority] || PRIORITY_DOT.low;
    const isMeal = r.type === 'meal_timing';
    const actions = r.actions || [];

    const actionsHtml = actions.length === 0 ? '' :
        isMeal
            ? `<div class="rec-options">
                ${actions.map((a, i) => `
                    <div class="rec-option">
                        <span class="rec-option-num">${i + 1}</span>
                        <span class="rec-option-text">${a}</span>
                    </div>`).join('')}
               </div>`
            : `<ul class="rec-actions">
                ${actions.map(a => `<li>${a}</li>`).join('')}
               </ul>`;

    return `
        <div class="rec-card ${meta.accent} rec-priority-${r.priority || 'low'}"
             onclick="toggleRecCard(this)">
            <div class="rec-header">
                <span class="rec-emoji">${r.emoji || ''}</span>
                <div class="rec-header-text">
                    <span class="rec-title">${r.title}</span>
                    <span class="rec-badge">${meta.badge}</span>
                </div>
                ${dot}
                <span class="rec-toggle">+</span>
            </div>
            <div class="rec-body">
                <p class="rec-message">${r.message}</p>
                ${actionsHtml}
            </div>
        </div>
    `;
}
// function buildRecCard(r) {
//     const meta     = REC_TYPE_META[r.type] || REC_TYPE_META.nutrient;
//     const dot      = PRIORITY_DOT[r.priority] || PRIORITY_DOT.low;
//     const isMeal   = r.type === 'meal_timing';
//     const actions  = r.actions || [];

//     // Dinner options (meal_timing) → numbered choice cards
//     const actionsHtml = actions.length === 0 ? '' :
//         isMeal
//             ? `<div class="rec-options">
//                 ${actions.map((a, i) => `
//                     <div class="rec-option">
//                         <span class="rec-option-num">${i + 1}</span>
//                         <span class="rec-option-text">${a}</span>
//                     </div>`).join('')}
//                </div>`
//             : `<ul class="rec-actions">
//                 ${actions.map(a => `<li>${a}</li>`).join('')}
//                </ul>`;

//     return `
//         <div class="rec-card ${meta.accent} rec-priority-${r.priority || 'low'}">
//             <div class="rec-header">
//                 <span class="rec-emoji">${r.emoji || ''}</span>
//                 <div class="rec-header-text">
//                     <span class="rec-title">${r.title}</span>
//                     <span class="rec-badge">${meta.badge}</span>
//                 </div>
//                 ${dot}
//             </div>
//             <p class="rec-message">${r.message}</p>
//             ${actionsHtml}
//         </div>
//     `;
// }

// ── Load fitness data ─────────────────────────────────
async function loadFitnessData() {
    try {
        const res  = await fetch('/fitness');
        const data = await res.json();
        if (data.error) return null;
        return data;
    } catch (e) {
        return null;
    }
}

// ── 3. REPLACE buildFitnessPanel() ──────────────────────────────────────────
function buildFitnessPanel(data) {
    if (!data) return '';

    const fit  = data.fitness          || {};
    const recs = data.recommendations  || {};

    const statsHtml = fit.available ? `
        <div class="fitness-stats-row">
            <div class="fitness-stat">
                <span class="fitness-stat-val">${(fit.steps || 0).toLocaleString()}</span>
                <span class="fitness-stat-lbl">Steps</span>
            </div>
            <div class="fitness-stat">
                <span class="fitness-stat-val">${fit.calories_burned || 0}</span>
                <span class="fitness-stat-lbl">kcal Active</span>
            </div>
            <div class="fitness-stat activity-stat">
                <span class="fitness-stat-val">${fit.activity_emoji || '—'}</span>
                <span class="fitness-stat-lbl">${fit.activity_label || 'Unknown'}</span>
            </div>
        </div>
        <div class="fitness-calorie-bar">
            <div class="fitness-calorie-row">
                <span>🍽️ Consumed</span>
                <span class="fitness-cal-num">${recs.cal_consumed || 0} kcal</span>
            </div>
            <div class="fitness-calorie-row">
                <span>🔥 Active Burn</span>
                <span class="fitness-cal-num">${fit.calories_burned || 0} kcal</span>
            </div>
            <div class="fitness-calorie-row" style="font-size:0.70rem;opacity:0.55">
                <span>&nbsp;&nbsp;↳ Total incl. BMR</span>
                <span class="fitness-cal-num">${fit.calories_total || 0} kcal</span>
            </div>
            <div class="fitness-calorie-divider"></div>
            <div class="fitness-calorie-row fitness-calorie-remaining">
                <span>⚡ Remaining</span>
                <span class="fitness-cal-num ${(recs.cal_remaining || 0) < 0 ? 'cal-over' : 'cal-ok'}">
                    ${(recs.cal_remaining || 0) >= 0
                        ? `${recs.cal_remaining} kcal to go`
                        : `${Math.abs(recs.cal_remaining)} kcal over`}
                </span>
            </div>
        </div>
    ` : `
        <div class="fitness-unavailable">
            <span>📱</span>
            <span>Connect Google Fit to see activity data</span>
        </div>
    `;

    const recsHtml = (recs.recommendations || [])
        .map(r => buildRecCard(r))
        .join('');

    return `
        <div class="fitness-card">
            <div class="gap-card-title">🏃 Activity & Smart Recommendations</div>
            ${statsHtml}
        </div>
        ${recsHtml ? `
            <div class="recs-section">
                <div class="recs-section-label">💡 Personalised Recommendations</div>
                ${recsHtml}
            </div>
        ` : ''}
    `;
}

// // ── Build fitness + recommendations panel ─────────────
// function buildFitnessPanel(data) {
//     if (!data) return '';

//     const fit  = data.fitness || {};
//     const recs = data.recommendations || {};

//     // Fitness stats row
//     const statsHtml = fit.available ? `
//         <div class="fitness-stats-row">
//             <div class="fitness-stat">
//                 <span class="fitness-stat-val">${(fit.steps || 0).toLocaleString()}</span>
//                 <span class="fitness-stat-lbl">Steps</span>
//             </div>
//             <div class="fitness-stat">
//                 <span class="fitness-stat-val">${fit.calories_burned || 0}</span>
//                 <span class="fitness-stat-lbl">kcal Burned</span>
//             </div>
//             <div class="fitness-stat activity-stat">
//                 <span class="fitness-stat-val">${fit.activity_emoji || ''}</span>
//                 <span class="fitness-stat-lbl">${fit.activity_label || ''}</span>
//             </div>
//         </div>
//         <div class="fitness-calorie-bar">
//             <div class="fitness-calorie-row">
//                 <span>🍽️ Eaten</span>
//                 <span class="fitness-cal-num">${recs.cal_consumed || 0} kcal</span>
//             </div>
//             <div class="fitness-calorie-row">
//                 <span>🔥 Active Burned</span>
//                 <span class="fitness-cal-num">${fit.calories_burned || 0} kcal</span>
//             </div>
//             <div class="fitness-calorie-row" style="font-size:0.72rem;opacity:0.65">
//                 <span>&nbsp;&nbsp;↳ Total incl. BMR</span>
//                 <span class="fitness-cal-num">${fit.calories_total || 0} kcal</span>
//             </div>

//             <div class="fitness-calorie-divider"></div>
//             <div class="fitness-calorie-row fitness-calorie-remaining">
//                 <span>⚡ Remaining</span>
//                 <span class="fitness-cal-num ${(recs.cal_remaining || 0) < 0 ? 'cal-over' : 'cal-ok'}">
//                     ${recs.cal_remaining >= 0
//                         ? `${recs.cal_remaining} kcal to go`
//                         : `${Math.abs(recs.cal_remaining)} kcal over`}
//                 </span>
//             </div>
//         </div>
//     ` : `
//         <div class="fitness-unavailable">
//             <span>📱</span>
//             <span>Connect Google Fit to see activity data</span>
//         </div>
//     `;

//     // Recommendations
//     const recsHtml = (recs.recommendations || []).map(r => `
//         <div class="rec-card rec-${r.priority || 'low'}">
//             <div class="rec-header">
//                 <span class="rec-emoji">${r.emoji}</span>
//                 <span class="rec-title">${r.title}</span>
//             </div>
//             <p class="rec-message">${r.message}</p>
//             ${r.actions && r.actions.length ? `
//                 <ul class="rec-actions">
//                     ${r.actions.map(a => `<li>${a}</li>`).join('')}
//                 </ul>
//             ` : ''}
//         </div>
//     `).join('');

//     return `
//         <div class="fitness-card">
//             <div class="gap-card-title">🏃 Activity & Smart Recommendations</div>
//             ${statsHtml}
//         </div>
//         ${recsHtml ? `
//             <div class="recs-section">
//                 <div class="gap-card-title" style="padding:0 4px 8px">💡 Personalized Recommendations</div>
//                 ${recsHtml}
//             </div>
//         ` : ''}
//     `;
// }

// ── Update loadHistory to include fitness ─────────────
// Replace your existing loadHistory with this:
// ── 2. REPLACE loadHistory() ────────────────────────────────────────────────
async function loadHistory() {
    const container = document.getElementById('history-list');
    container.innerHTML = `
        <div class="history-skeleton">
            <div class="skeleton-card">
                <div class="sk sk-title"></div>
                <div class="sk sk-bar"></div>
                <div class="sk sk-bar sk-bar-short"></div>
            </div>
        </div>`;

    updateDateNavLabel();

    try {
        const targetDate = getHistoryDate(historyDateOffset);
        const isToday    = historyDateOffset === 0;

        const fetches = [
            fetch(`/history/daily?date=${targetDate}`),
            fetch('/history'),
        ];
        if (isToday) fetches.push(loadFitnessData());

        const results  = await Promise.all(fetches);
        const daily    = await results[0].json();
        const all      = await results[1].json();
        const fitnessData = isToday ? results[2] : null;

        if (daily.error) {
            container.innerHTML = `<p class="hint" style="padding:16px">Error: ${daily.error}</p>`;
            return;
        }

        container.innerHTML = [
            isToday ? buildFitnessPanel(fitnessData) : '',
            buildDailyGaps(daily),
            buildTimeline(daily),
            buildPastMeals(all, targetDate),
        ].filter(Boolean).join('');

    } catch (e) {
        container.innerHTML = `<p class="hint" style="padding:16px">Could not load: ${e.message}</p>`;
    }
}


// ── Daily nutrition gap summary ───────────────────────
function buildDailyGaps(daily) {
    const gaps   = daily.gaps || [];
    const totals = daily.daily_totals || {};
    const targets = daily.daily_targets || {};

    if (!gaps.length) {
        return `<div class="gap-card gap-card-empty">
            <div class="gap-card-title">📊 Today's Nutrition</div>
            <p class="hint">No meals logged today yet.</p>
        </div>`;
    }

    // Progress bars for key macros
    const macros = ['calories','protein','carbs','fat','fibre'];
    const macroLabels = {
        calories:'Calories', protein:'Protein', carbs:'Carbs', fat:'Fat', fibre:'Fibre'
    };
    const macroUnits = {
        calories:'kcal', protein:'g', carbs:'g', fat:'g', fibre:'g'
    };

    const progressBars = macros.map(key => {
        const consumed = totals[key] || 0;
        const target   = targets[key] || 1;
        const pct      = Math.min(100, Math.round(consumed / target * 100));
        const color    = pct >= 90 ? '#2d8f58' : pct >= 60 ? '#e8762a' : '#dc2626';
        return `
            <div class="macro-progress-row">
                <div class="macro-progress-label">
                    <span>${macroLabels[key]}</span>
                    <span class="macro-progress-val">${Math.round(consumed)} / ${target} ${macroUnits[key]}</span>
                </div>
                <div class="macro-progress-bar-bg">
                    <div class="macro-progress-bar-fill" style="width:${pct}%;background:${color}"></div>
                </div>
            </div>
        `;
    }).join('');

    // Alert messages (non-good)
    const alerts = gaps.filter(g => g.severity !== 'good');
    const alertsHtml = alerts.length ? alerts.map(a => `
        <div class="gap-alert gap-alert-${a.severity}">
            <span class="gap-alert-icon">${severityIcon(a.severity)}</span>
            <div>
                <strong>${a.label}</strong>
                ${a.consumed > 0
                    ? `<span class="gap-alert-nums">${a.consumed}${a.unit} / ${a.target}${a.unit} (${a.pct}%)</span>`
                    : ''}
                <p class="gap-alert-msg">${a.message}</p>
            </div>
        </div>
    `).join('') : '<p class="hint" style="margin-top:8px">✅ All nutrients on track today!</p>';

    return `
        <div class="gap-card">
            <div class="gap-card-title">📊 Today's Progress — ${daily.date}</div>
            <div class="gap-meal-count">${daily.meal_count} meal${daily.meal_count !== 1 ? 's' : ''} logged</div>
            <div class="macro-progress-stack">${progressBars}</div>
            <div class="gap-alerts-section">
                <div class="gap-alerts-title">⚡ Nutrition Alerts</div>
                ${alertsHtml}
            </div>
        </div>
    `;
}

function severityIcon(s) {
    if (s === 'high')    return '🔴';
    if (s === 'medium')  return '🟠';
    if (s === 'warning') return '⚠️';
    if (s === 'caution') return '🟡';
    return '✅';
}

// ── Today's timeline ──────────────────────────────────
function buildTimeline(daily) {
    const timeline = daily.timeline || [];
    if (!timeline.length) return '';

    const categoryIcons = {
        'Breakfast':       '🌅',
        'Morning Snack':   '☕',
        'Lunch':           '☀️',
        'Afternoon Snack': '🍎',
        'Dinner':          '🌙',
        'Late Snack':      '🌚',
    };

    const sections = timeline.map(cat => {
        const icon  = categoryIcons[cat.category] || '🍽️';
        const meals = cat.meals.map(meal => `
            <div class="timeline-meal">
                <div class="timeline-meal-time">${meal.timestamp ? meal.timestamp.slice(11,16) : ''}</div>
                <div class="timeline-meal-body">
                    <div class="timeline-meal-desc">${meal.meal_description || 'Meal'}</div>
                    <div class="timeline-meal-foods">
                        ${(meal.foods || []).map(f => `${f.name} (${f.grams}g)`).join(' · ')}
                    </div>
                    <div class="timeline-meal-cal">🔥 ${meal.total_calories || 0} kcal</div>
                </div>
            </div>
        `).join('');

        const t = cat.totals;
        return `
            <div class="timeline-section">
                <div class="timeline-section-header">
                    <span class="timeline-icon">${icon}</span>
                    <span class="timeline-cat-name">${cat.category}</span>
                    <span class="timeline-cat-cal">${Math.round(t.calories || 0)} kcal</span>
                </div>
                <div class="timeline-meals">${meals}</div>
                <div class="timeline-section-totals">
                    P: ${(t.protein||0).toFixed(1)}g &nbsp;|&nbsp;
                    C: ${(t.carbs||0).toFixed(1)}g &nbsp;|&nbsp;
                    F: ${(t.fat||0).toFixed(1)}g &nbsp;|&nbsp;
                    Fibre: ${(t.fibre||0).toFixed(1)}g
                </div>
            </div>
        `;
    }).join('');

    return `
        <div class="timeline-card">
            <div class="gap-card-title">🕐 Today's Timeline</div>
            ${sections}
        </div>
    `;
}

// ── Past meals (previous days) ────────────────────────
function buildPastMeals(all, today) {
    const past = [...all].reverse().filter(m =>
        !m.timestamp || !m.timestamp.startsWith(today)
    ).slice(0, 10);

    if (!past.length) return '';

    const items = past.map(m => `
        <div class="history-item">
            <div class="history-date">📅 ${m.timestamp || ''} · ${m.meal_category || 'Meal'}</div>
            <div class="history-desc">${m.meal_description || 'Meal'}</div>
            <div class="history-foods">${(m.foods||[]).map(f=>`${f.name} (${f.grams}g)`).join(' · ')}</div>
            <div class="history-meta">
                <span class="history-cal">🔥 ${m.total_calories || 0} kcal</span>
            </div>
        </div>
    `).join('');

    return `
        <div class="card" style="margin-top:12px">
            <div class="card-label">📆 Previous Meals</div>
            ${items}
        </div>
    `;
}

// ── Helpers ──────────────────────────────────────
function showLoading(show) {
    document.getElementById('loading').style.display = show ? 'block' : 'none';
}

function resetApp() {
    currentImageBase64 = null;
    voiceText = '';
    clearError();
    document.getElementById('photo-preview').style.display     = 'none';
    document.getElementById('camera-preview').style.display    = 'none';
    document.getElementById('camera-placeholder').style.display = 'block';
    document.getElementById('analyze-btn').style.display       = 'none';
    document.getElementById('analyze-voice-btn').style.display = 'none';
    document.getElementById('results').style.display           = 'none';
    document.getElementById('voice-text').textContent          = '';
    document.getElementById('capture-btn').style.display       = 'none';
        enableOpenAIOption();
}

// ── PWA ──────────────────────────────────────────
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
});


// ── Mode Selector ─────────────────────────────
// Switches between Health and Gut personas

function initModeSelector() {
    const radios = document.querySelectorAll('input[name="app-mode"]');
    
    // Restore saved mode
    const savedMode = localStorage.getItem('appMode') || 'health';
    document.querySelector(`input[value="${savedMode}"]`).checked = true;
    applyMode(savedMode);

    // Listen for changes
    radios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            applyMode(e.target.value);
            localStorage.setItem('appMode', e.target.value);
        });
    });
}

function applyMode(mode) {
    const healthContent = document.getElementById('health-mode-content');
    const gutContent = document.getElementById('gut-mode-content');

    if (mode === 'gut') {
        healthContent.style.display = 'none';
        gutContent.style.display = 'block';
        // Load gut JS if not already loaded
        if (!window.gutAppLoaded) loadGutApp();
    } else {
        healthContent.style.display = 'block';
        gutContent.style.display = 'none';
    }
}

function loadGutApp() {
    // Dynamically load gut_app.js only when needed
    // Keeps initial load fast for health mode users
    const script = document.createElement('script');
    script.src = '/static/js/gut_app.js';
    script.onload = () => {
        window.gutAppLoaded = true;
        if (typeof initGutMode === 'function') initGutMode();
    };
    document.head.appendChild(script);
}

// Initialise on page load
document.addEventListener('DOMContentLoaded', initModeSelector);