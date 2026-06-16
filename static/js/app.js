// ══════════════════════════════════════════════════
// app.js  —  Health Tracker (Persona 1)
// Gut tracker logic lives in gut_app.js
// ══════════════════════════════════════════════════

// ── Global state ─────────────────────────────────
let historyDateOffset  = 0;
let currentMealTimestamp = null;
let currentCuisineType   = null;
let currentGutScore      = 0;
let currentGutNotes      = '';
let currentImageBase64   = null;
let currentMimeType      = 'image/jpeg';
let currentImageWidth    = 0;
let currentImageHeight   = 0;
let voiceRecognition     = null;
let isRecording          = false;
let voiceText            = '';
let currentResults       = [];

const MAX_CLIENT_FILE_BYTES = 8 * 1024 * 1024;
const MAX_CLIENT_DIMENSION  = { w: 4000, h: 3000 };

window.addEventListener('DOMContentLoaded', async () => {
    await initPinAuth();  // ← must be FIRST, before anything else
    // ... rest of your existing init code
});

// ── Timezone helpers ──────────────────────────────
function getUserTimezone() {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

function formatLocalTime(timestampStr) {
    if (!timestampStr) return '';
    try {
        const date = new Date(timestampStr.replace(' ', 'T'));
        return date.toLocaleString(undefined, {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', hour12: true
        });
    } catch (e) { return timestampStr; }
}

function getHistoryDate(offset = 0) {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    return d.toLocaleDateString('en-CA'); // YYYY-MM-DD in local TZ
}

// ── Error / message banner ────────────────────────
function showError(message) {
    const el = document.getElementById('error-message');
    el.textContent = message;
    el.style.cssText = 'display:block;background:#fee2e2;color:#991b1b;border-color:#fca5a5';
}

function showMessage(message) {
    const el = document.getElementById('error-message');
    el.textContent = message;
    el.style.cssText = 'display:block;background:#ecfdf5;color:#166534;border-color:#a7f3d0';
}

function clearError() {
    const el = document.getElementById('error-message');
    el.textContent = '';
    el.style.display = 'none';
}

// ── Mode helpers ──────────────────────────────────
function getCurrentMode() {
    return localStorage.getItem('appMode') || 'health';
}

/**
 * Show the correct analyze button(s) after an image is loaded.
 * Called from capturePhoto() and handleFileUpload().
 */
function showCorrectAnalyzeButton() {
    const mode      = getCurrentMode();
    const healthBtn = document.getElementById('analyze-btn');
    const gutBtn    = document.getElementById('gut-analyze-btn');
    if (mode === 'gut') {
        if (healthBtn) healthBtn.style.display = 'none';
        if (gutBtn)    gutBtn.style.display    = 'block';
    } else {
        if (gutBtn)    gutBtn.style.display    = 'none';
        if (healthBtn) healthBtn.style.display = 'block';
    }
}

/**
 * Hide ALL analyze / voice buttons and reset photo UI.
 * Called from resetApp() and gutRejectResults().
 */
function hideAllAnalyzeButtons() {
    ['analyze-btn', 'gut-analyze-btn',
     'analyze-voice-btn', 'gut-analyze-voice-btn'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
}

// ── Nutrition row calc ────────────────────────────
function calculateRowNutrition(row) {
    const g    = row.grams || 0;
    const base = row.per100 || {};
    const cal  = base.energy_kcal || base.calories || 0;
    const carb = base.carbohydrates || base.carbs  || 0;
    return {
        ...row,
        calories:    Number((cal  * g / 100).toFixed(1)),
        protein:     Number(((base.protein    || 0) * g / 100).toFixed(1)),
        carbs:       Number((carb             * g / 100).toFixed(1)),
        fat:         Number(((base.fat        || 0) * g / 100).toFixed(1)),
        fibre:       Number(((base.fibre      || 0) * g / 100).toFixed(1)),
        sugars:      Number(((base.sugars     || 0) * g / 100).toFixed(1)),
        sodium:      Number(((base.sodium     || 0) * g / 100).toFixed(1)),
        calcium:     Number(((base.calcium    || 0) * g / 100).toFixed(1)),
        iron:        Number(((base.iron       || 0) * g / 100).toFixed(2)),
        magnesium:   Number(((base.magnesium  || 0) * g / 100).toFixed(1)),
        potassium:   Number(((base.potassium  || 0) * g / 100).toFixed(1)),
        zinc:        Number(((base.zinc       || 0) * g / 100).toFixed(2)),
        vitamin_a:   Number(((base.vitamin_a  || 0) * g / 100).toFixed(1)),
        vitamin_c:   Number(((base.vitamin_c  || 0) * g / 100).toFixed(1)),
        vitamin_d:   Number(((base.vitamin_d  || 0) * g / 100).toFixed(2)),
        vitamin_e:   Number(((base.vitamin_e  || 0) * g / 100).toFixed(2)),
        cholesterol: Number(((base.cholesterol|| 0) * g / 100).toFixed(1))
    };
}

function handleResultEdit(index, field, value) {
    if (!currentResults[index]) return;
    if (field === 'grams') {
        const g = Number(value);
        currentResults[index].grams = isNaN(g) ? 0 : g;
        currentResults[index] = calculateRowNutrition(currentResults[index]);
        updateRowCells(index);
        refreshTotals();
    } else if (field === 'name') {
        currentResults[index].name = value;
    }
}

function updateRowCells(index) {
    const f   = currentResults[index];
    const row = document.querySelector(`#foods-list tr:nth-child(${index + 1})`);
    if (!row) return;
    const c = row.querySelectorAll('td');
    if (c[2]) c[2].textContent = Math.round(f.calories);
    if (c[3]) c[3].textContent = f.protein.toFixed(1)  + 'g';
    if (c[4]) c[4].textContent = f.carbs.toFixed(1)    + 'g';
    if (c[5]) c[5].textContent = f.sugars.toFixed(1)   + 'g';
    if (c[6]) c[6].textContent = f.fat.toFixed(1)      + 'g';
    if (c[7]) c[7].textContent = f.fibre.toFixed(1)    + 'g';

    const mr = document.querySelector(`#micro-list tr:nth-child(${index + 1})`);
    if (mr) {
        const m = mr.querySelectorAll('td');
        if (m[1])  m[1].textContent  = f.sodium.toFixed(1);
        if (m[2])  m[2].textContent  = f.calcium.toFixed(1);
        if (m[3])  m[3].textContent  = f.iron.toFixed(2);
        if (m[4])  m[4].textContent  = f.magnesium.toFixed(1);
        if (m[5])  m[5].textContent  = f.potassium.toFixed(1);
        if (m[6])  m[6].textContent  = f.zinc.toFixed(2);
        if (m[7])  m[7].textContent  = f.vitamin_a.toFixed(1);
        if (m[8])  m[8].textContent  = f.vitamin_c.toFixed(1);
        if (m[9])  m[9].textContent  = f.vitamin_d.toFixed(2);
        if (m[10]) m[10].textContent = f.vitamin_e.toFixed(2);
        if (m[11]) m[11].textContent = f.cholesterol.toFixed(1);
    }
}

function toggleRecCard(card) {
    const isOpen = card.classList.toggle('rec-open');
    card.querySelector('.rec-toggle').textContent = isOpen ? '−' : '+';
}

// ── Recalculate / add / remove food ──────────────
async function recalculateNutrition() {
    if (!currentResults.length) {
        showError('No results to recalculate.'); return;
    }
    clearError();
    showLoading(true);
    try {
        const res  = await fetch('/recalculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ foods: currentResults.map(({ name, grams }) => ({ name, grams })) })
        });
        const data = await res.json();
        if (data.error) { showError('Error: ' + data.error); return; }
        if (!Array.isArray(data.foods)) {
            showError('Unexpected response.'); return;
        }
        currentResults = data.foods.map(f => {
            const grams  = Number(f.grams) || 0;
            const per100 = f.per100 || {
                energy_kcal:    grams ? (Number(f.calories)     || 0) * 100 / grams : 0,
                protein:        grams ? (Number(f.protein)      || 0) * 100 / grams : 0,
                carbohydrates:  grams ? (Number(f.carbs)        || 0) * 100 / grams : 0,
                fat:            grams ? (Number(f.fat)          || 0) * 100 / grams : 0,
                fibre:          grams ? (Number(f.fibre)        || 0) * 100 / grams : 0,
                sugars:         grams ? (Number(f.sugars)       || 0) * 100 / grams : 0,
                sodium:         grams ? (Number(f.sodium)       || 0) * 100 / grams : 0,
                calcium:        grams ? (Number(f.calcium)      || 0) * 100 / grams : 0,
                iron:           grams ? (Number(f.iron)         || 0) * 100 / grams : 0,
                magnesium:      grams ? (Number(f.magnesium)    || 0) * 100 / grams : 0,
                potassium:      grams ? (Number(f.potassium)    || 0) * 100 / grams : 0,
                zinc:           grams ? (Number(f.zinc)         || 0) * 100 / grams : 0,
                vitamin_a:      grams ? (Number(f.vitamin_a)    || 0) * 100 / grams : 0,
                vitamin_c:      grams ? (Number(f.vitamin_c)    || 0) * 100 / grams : 0,
                vitamin_d:      grams ? (Number(f.vitamin_d)    || 0) * 100 / grams : 0,
                vitamin_e:      grams ? (Number(f.vitamin_e)    || 0) * 100 / grams : 0,
                cholesterol:    grams ? (Number(f.cholesterol)  || 0) * 100 / grams : 0
            };
            return calculateRowNutrition({ ...f, grams, per100 });
        });
        renderResultRows();
        showMessage('Nutrition recalculated.');
    } catch (err) {
        showError('Recalculation failed: ' + err.message);
    } finally {
        showLoading(false);
    }
}

function removeFood(index) {
    currentResults.splice(index, 1);
    renderResultRows();
}

async function addNewFood() {
    const nameInput  = document.getElementById('new-food-name');
    const gramsInput = document.getElementById('new-food-grams');
    const name       = nameInput.value.trim();
    const grams      = Number(gramsInput.value) || 100;
    if (!name) { showError('Please enter a food name'); return; }

    showLoading(true);
    try {
        const res  = await fetch('/recalculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ foods: [{ name, grams }] })
        });
        const data = await res.json();
        if (data.foods && data.foods[0]) {
            const f      = data.foods[0];
            const per100 = f.per100 || {};
            currentResults.push(calculateRowNutrition({ ...f, grams, per100 }));
            renderResultRows();
            nameInput.value  = '';
            gramsInput.value = '100';
            if (!f.found_in_db) {
                showError(`"${name}" not in database — added with zero values.`);
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
    const foodsHtml = currentResults.map((f, i) => `
        <tr>
            <td>
                <input type="text" class="food-edit"
                       value="${f.name}"
                       data-index="${i}" data-field="name"/>
                ${f.matched && f.matched !== f.name
                    ? `<div style="font-size:0.7rem;color:var(--gray-400)">
                           Matched: ${f.matched}
                       </div>` : ''}
                ${!f.found_in_db
                    ? '<span class="not-in-db">~</span>' : ''}
            </td>
            <td>
                <input type="number" min="0" class="amount-edit"
                       value="${f.grams}"
                       data-index="${i}" data-field="grams"/>
            </td>
            <td class="kcal-cell">${Math.round(f.calories)}</td>
            <td>${f.protein.toFixed(1)}g</td>
            <td>${f.carbs.toFixed(1)}g</td>
            <td>${f.sugars.toFixed(1)}g</td>
            <td>${f.fat.toFixed(1)}g</td>
            <td>${f.fibre.toFixed(1)}g</td>
            <td>
                <button class="remove-food-btn"
                        data-index="${i}"
                        title="Remove">✕</button>
            </td>
        </tr>`).join('');

    const microHtml = currentResults.map(f => `
        <tr>
            <td>${f.name.length > 20
                ? f.name.substring(0,20) + '…' : f.name}</td>
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
        </tr>`).join('');

    document.getElementById('foods-list').innerHTML = foodsHtml;
    document.getElementById('micro-list').innerHTML = microHtml;

    document.querySelectorAll('.food-edit, .amount-edit').forEach(inp => {
        inp.addEventListener('input', e => {
            handleResultEdit(
                Number(e.target.dataset.index),
                e.target.dataset.field,
                e.target.value
            );
        });
    });

    document.querySelectorAll('.remove-food-btn').forEach(btn => {
        btn.addEventListener('click', e => {
            removeFood(Number(e.target.dataset.index));
        });
    });

    refreshTotals();
}

function refreshTotals() {
    const t = {
        cal:0, protein:0, carbs:0, fat:0, fibre:0, sugars:0,
        sodium:0, calcium:0, iron:0, magnesium:0, potassium:0,
        zinc:0, vitamin_a:0, vitamin_c:0, vitamin_d:0,
        vitamin_e:0, cholesterol:0
    };
    currentResults.forEach(f => {
        t.cal         += f.calories    || 0;
        t.protein     += f.protein     || 0;
        t.carbs       += f.carbs       || 0;
        t.fat         += f.fat         || 0;
        t.fibre       += f.fibre       || 0;
        t.sugars      += f.sugars      || 0;
        t.sodium      += f.sodium      || 0;
        t.calcium     += f.calcium     || 0;
        t.iron        += f.iron        || 0;
        t.magnesium   += f.magnesium   || 0;
        t.potassium   += f.potassium   || 0;
        t.zinc        += f.zinc        || 0;
        t.vitamin_a   += f.vitamin_a   || 0;
        t.vitamin_c   += f.vitamin_c   || 0;
        t.vitamin_d   += f.vitamin_d   || 0;
        t.vitamin_e   += f.vitamin_e   || 0;
        t.cholesterol += f.cholesterol || 0;
    });

    const set = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.textContent = v;
    };
    set('summary-cal',     Math.round(t.cal) + ' kcal');
    set('summary-protein', t.protein.toFixed(1) + 'g');
    set('summary-carbs',   t.carbs.toFixed(1) + 'g');
    set('summary-fat',     t.fat.toFixed(1) + 'g');
    set('total-cal',       Math.round(t.cal));
    set('total-protein',   t.protein.toFixed(1) + 'g');
    set('total-carbs',     t.carbs.toFixed(1) + 'g');
    set('total-sugars',    t.sugars.toFixed(1) + 'g');
    set('total-fat',       t.fat.toFixed(1) + 'g');
    set('total-fibre',     t.fibre.toFixed(1) + 'g');
    set('total-sodium',    t.sodium.toFixed(1));
    set('total-calcium',   t.calcium.toFixed(1));
    set('total-iron',      t.iron.toFixed(2));
    set('total-magnesium', t.magnesium.toFixed(1));
    set('total-potassium', t.potassium.toFixed(1));
    set('total-zinc',      t.zinc.toFixed(2));
    set('total-vitamin-a', t.vitamin_a.toFixed(1));
    set('total-vitamin-c', t.vitamin_c.toFixed(1));
    set('total-vitamin-d', t.vitamin_d.toFixed(2));
    set('total-vitamin-e', t.vitamin_e.toFixed(2));
    set('total-cholesterol', t.cholesterol.toFixed(1));
}

// ── Tabs ──────────────────────────────────────────
function showTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    event.target.classList.add('active');
    if (tab === 'history') {
        historyDateOffset = 0;
        loadHistory();
    }
}

// ── Camera ────────────────────────────────────────
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'environment',
                width:      { ideal: 1920 },
                height:     { ideal: 1080 },
                focusMode:  { ideal: 'continuous' },
                advanced:   [{ focusMode: 'continuous' }]
            }
        });
        const video = document.getElementById('camera-preview');
        video.srcObject = stream;
        video.style.display   = 'block';
        document.getElementById('photo-preview').style.display       = 'none';
        document.getElementById('camera-placeholder').style.display  = 'none';
        document.getElementById('capture-btn').style.display         = 'block';
        hideAllAnalyzeButtons();
        currentImageBase64 = null;
    } catch (err) {
        alert('Camera access denied. Please use Upload Photo instead.');
    }
}

function capturePhoto() {
    const video  = document.getElementById('camera-preview');
    const canvas = document.getElementById('canvas');
    canvas.width  = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    video.srcObject.getTracks().forEach(t => t.stop());
    video.style.display = 'none';

    const imageData = canvas.toDataURL('image/jpeg', 0.8);
    const preview   = document.getElementById('photo-preview');
    preview.src     = imageData;
    preview.style.display = 'block';

    currentImageBase64 = imageData.split(',')[1];
    currentMimeType    = 'image/jpeg';
    currentImageWidth  = canvas.width;
    currentImageHeight = canvas.height;

    const opt = document.querySelector('#provider-select option[value="openai"]');
    if (opt) {
        opt.disabled = true;
        const sel = document.getElementById('provider-select');
        if (sel && sel.value === 'openai') {
            sel.value = 'gemini';
            showError('OpenAI vision disabled. Switched to Gemini.');
        }
    }

    document.getElementById('capture-btn').style.display = 'none';
    showCorrectAnalyzeButton();

    // ── Update overlay footer to show Use Photo button ──
    const footer = document.querySelector('.camera-overlay-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="camera-btn-secondary"
                    onclick="retakePhoto()">
                ↩ Retake
            </button>
            <button class="camera-btn-primary"
                    onclick="usePhoto()">
                ✅ Use Photo
            </button>`;
    }
}

function retakePhoto() {
    // Reset and reopen camera
    const footer = document.querySelector('.camera-overlay-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="camera-btn-secondary"
                    onclick="closeCameraOverlay()">Cancel</button>
            <button class="camera-btn-capture"
                    id="capture-btn"
                    style="display:none"
                    onclick="capturePhoto()">⬤</button>
            <button class="camera-btn-primary"
                    onclick="startCamera()">📷 Open Camera</button>`;
    }
    startCamera();
}

function usePhoto() {
    closeCameraOverlay();

    const mainPreview = document.getElementById('main-photo-preview');
    const mainImg     = document.getElementById('main-photo-img');

    if (mainPreview && mainImg && currentImageBase64) {
        mainImg.src               = `data:image/jpeg;base64,${currentImageBase64}`;
        mainPreview.style.display = 'block';
    }

    showCorrectAnalyzeButton();
}

function clearPhoto() {
    currentImageBase64 = null;
    const mainPreview  = document.getElementById('main-photo-preview');
    if (mainPreview) mainPreview.style.display = 'none';
    hideAllAnalyzeButtons();
}


function uploadPhoto() {
    document.getElementById('file-input').click();
}

function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    currentMimeType = file.type || 'image/jpeg';

    if (file.size > MAX_CLIENT_FILE_BYTES) {
        if (file.size > 20 * 1024 * 1024) {
            showError('Image too large (>20MB). Choose a smaller photo.');
            return;
        }
        showError('Large image — the app will downscale it.');
    }

    const processBitmap = async (bitmap) => {
        try {
            const maxW = 1200, maxH = 900;
            const ratio = Math.min(maxW / bitmap.width, maxH / bitmap.height, 1);
            const tw    = Math.max(1, Math.round(bitmap.width  * ratio));
            const th    = Math.max(1, Math.round(bitmap.height * ratio));
            const canvas = document.createElement('canvas');
            canvas.width  = tw;
            canvas.height = th;
            canvas.getContext('2d').drawImage(bitmap, 0, 0, tw, th);
            if (bitmap.close) try { bitmap.close(); } catch (e) {}

            const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
            currentImageBase64 = dataUrl.split(',')[1];
            currentImageWidth  = tw;
            currentImageHeight = th;

            document.getElementById('photo-preview').src           = dataUrl;
            document.getElementById('photo-preview').style.display = 'block';
            document.getElementById('camera-preview').style.display    = 'none';
            document.getElementById('camera-placeholder').style.display = 'none';

            // Disable OpenAI
            const opt = document.querySelector('#provider-select option[value="openai"]');
            if (opt) {
                opt.disabled = true;
                const sel = document.getElementById('provider-select');
                if (sel && sel.value === 'openai') {
                    sel.value = 'gemini';
                    showError('OpenAI vision disabled. Switched to Gemini.');
                }
            }

            showCorrectAnalyzeButton();
            // Show in main preview
            const mp = document.getElementById('main-photo-preview');
            const mi = document.getElementById('main-photo-img');
            if (mp && mi) { mi.src = dataUrl; mp.style.display = 'block'; }
        } catch (err) {
            showError('Failed to process image: ' + err.message);
        }
    };

    if (window.createImageBitmap) {
        createImageBitmap(file).then(processBitmap).catch(() => {
            const reader = new FileReader();
            reader.onload = e => {
                const img = new Image();
                img.onload = async () => {
                    try {
                        const b64 = await resizeImageBase64(
                            e.target.result.split(',')[1],
                            currentMimeType, 1200, 900, 0.8
                        );
                        document.getElementById('photo-preview').src =
                            `data:${currentMimeType};base64,${b64}`;
                        document.getElementById('photo-preview').style.display = 'block';
                        document.getElementById('camera-preview').style.display    = 'none';
                        document.getElementById('camera-placeholder').style.display = 'none';
                        currentImageBase64 = b64;
                        showCorrectAnalyzeButton();
                    } catch (e) {
                        showError('Image processing failed.');
                    }
                };
                img.onerror = () => showError('Could not load image.');
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        });
    } else {
        const reader = new FileReader();
        reader.onload = e => {
            resizeImageBase64(e.target.result.split(',')[1],
                              currentMimeType, 1200, 900, 0.8).then(b64 => {
                document.getElementById('photo-preview').src =
                    `data:${currentMimeType};base64,${b64}`;
                document.getElementById('photo-preview').style.display = 'block';
                document.getElementById('camera-preview').style.display    = 'none';
                document.getElementById('camera-placeholder').style.display = 'none';
                currentImageBase64 = b64;
                showCorrectAnalyzeButton();
            }).catch(() => showError('Image processing failed.'));
        };
        reader.readAsDataURL(file);
    }
}

function enableOpenAIOption() {
    const opt = document.querySelector('#provider-select option[value="openai"]');
    if (opt) opt.disabled = false;
}

function getSelectedProvider() {
    return document.getElementById('provider-select')?.value || 'gemini';
}

// ── Image utilities ───────────────────────────────
function resizeImageBase64(base64Data, mimeType='image/jpeg',
                            maxW=1200, maxH=900, quality=0.8) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            const ratio = Math.min(maxW / img.width, maxH / img.height, 1);
            const tw    = Math.max(1, Math.round(img.width  * ratio));
            const th    = Math.max(1, Math.round(img.height * ratio));
            const canvas = document.createElement('canvas');
            canvas.width  = tw;
            canvas.height = th;
            canvas.getContext('2d').drawImage(img, 0, 0, tw, th);
            try { resolve(canvas.toDataURL(mimeType, quality).split(',')[1]); }
            catch (e) { reject(e); }
        };
        img.onerror = e => reject(e);
        img.src = `data:${mimeType};base64,${base64Data}`;
    });
}

async function compressBase64ToLimit(base64Data, mimeType='image/jpeg',
                                     maxBytes=140*1024) {
    let q = 0.8;
    const img = new Image();
    img.src = `data:${mimeType};base64,${base64Data}`;
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; });
    const w = img.width, h = img.height;
    const bytes = Math.ceil(base64Data.length * 3 / 4);
    if (bytes <= maxBytes) return { base64: base64Data, width: w, height: h, compressed: false };

    for (let i = 0; i < 6; i++) {
        const canvas = document.createElement('canvas');
        const scale  = i >= 2 ? Math.pow(0.9, i - 1) : 1;
        canvas.width  = Math.max(1, Math.round(w * scale));
        canvas.height = Math.max(1, Math.round(h * scale));
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        try {
            const url = canvas.toDataURL(mimeType, q);
            const b64 = url.split(',')[1];
            if (Math.ceil(b64.length * 3 / 4) <= maxBytes)
                return { base64: b64, width: canvas.width, height: canvas.height, compressed: true };
            q = Math.max(0.2, q - 0.15);
            await new Promise(r => setTimeout(r, 50));
        } catch (e) { break; }
    }
    return { base64: base64Data, width: w, height: h, compressed: false };
}

// ── Analyze photo (health) ────────────────────────
async function analyzePhoto() {
    if (!currentImageBase64) {
        showError('Please take or upload a photo first!'); return;
    }
    clearError();
    showLoading(true);
    document.getElementById('analyze-btn').style.display = 'none';
    document.getElementById('results').style.display     = 'none';
    try {
        const resized     = await resizeImageBase64(currentImageBase64, currentMimeType, 1200, 900, 0.8);
        const compressed  = await compressBase64ToLimit(resized, currentMimeType, 140 * 1024);
        const sendBase64  = compressed.base64;
        if (compressed.width)  currentImageWidth  = compressed.width;
        if (compressed.height) currentImageHeight = compressed.height;
        if (compressed.compressed) showError('Image compressed to reduce upload size.');

        const bodyObj = {
            image: sendBase64, mime_type: currentMimeType,
            provider: getSelectedProvider(),
            image_width: currentImageWidth, image_height: currentImageHeight,
            timezone: getUserTimezone()
        };
        bodyObj.client_estimated_tokens = Math.ceil(JSON.stringify(bodyObj).length / 4);

        const res  = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bodyObj)
        });
        const data = await res.json();
        if (data.error) { showError('Error: ' + data.error); }
        else { showResults(data); }
    } catch (err) {
        showError('Something went wrong: ' + err.message);
    } finally {
        showLoading(false);
    }
}

// ── Type your meal ────────────────────────────────
function useTypedText() {
    const input = document.getElementById('manual-text-input');
    const text  = input.value.trim();
    if (!text) { showError('Please type your meal description first.'); return; }

    voiceText = text;
    document.getElementById('voice-text').textContent = text;
    input.value = '';

    const mode = getCurrentMode();
    if (mode === 'gut') {
        // Show gut voice analyze button
        document.getElementById('gut-analyze-voice-btn').style.display = 'block';
        document.getElementById('analyze-voice-btn').style.display     = 'none';
    } else {
        document.getElementById('analyze-voice-btn').style.display     = 'block';
        document.getElementById('gut-analyze-voice-btn').style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('manual-text-input');
    if (input) {
        input.addEventListener('keypress', e => {
            if (e.key === 'Enter') useTypedText();
        });
    }
});

// ── Voice ─────────────────────────────────────────
function toggleVoice() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert('Voice not supported. Try Chrome or Samsung Browser.'); return;
    }
    isRecording ? stopVoice() : startVoice();
}

function startVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    voiceRecognition = new SR();
    voiceRecognition.continuous     = false;
    voiceRecognition.interimResults = true;
    voiceRecognition.lang           = 'en-AU';

    voiceRecognition.onresult = e => {
        const t = Array.from(e.results)
                    .map(r => r[0].transcript)
                    .join('');
        voiceText = t;

        // Update the voice-text inside recording bar
        const voiceTextEl = document.getElementById('voice-text');
        if (voiceTextEl) voiceTextEl.textContent = t || 'Listening...';
    };

    voiceRecognition.onend = () => {
        isRecording = false;
        
        // Stop the pulse animation but KEEP bar visible
        const voiceBtn = document.getElementById('voice-action-btn');
        if (voiceBtn) voiceBtn.classList.remove('recording');

        if (voiceText.trim()) {
            // Show captured text — keep bar visible until analyze tapped
            const voiceTextEl = document.getElementById('voice-text');
            if (voiceTextEl) {
                voiceTextEl.textContent = `✅ "${voiceText.trim()}"`;
                voiceTextEl.style.color = '#0d5c38';
            }

            // Show analyze button
            const mode = getCurrentMode();
            if (mode === 'gut') {
                document.getElementById('gut-analyze-voice-btn')
                        .style.display = 'block';
                document.getElementById('analyze-voice-btn')
                        .style.display = 'none';
            } else {
                document.getElementById('analyze-voice-btn')
                        .style.display = 'block';
                document.getElementById('gut-analyze-voice-btn')
                        .style.display = 'none';
            }
        } else {
            updateVoiceUI(false);
        }
    };

    voiceRecognition.onerror = e => {
        isRecording = false;
        updateVoiceUI(false);
        if (e.error !== 'no-speech') {
            alert('Voice error: ' + e.error);
        }
    };

    updateVoiceUI(true);
    voiceRecognition.start();
    isRecording = true;
}
// function startVoice() {
//     voiceText = '';

//     const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
//     voiceRecognition = new SR();
//     voiceRecognition.continuous     = true;
//     voiceRecognition.interimResults = false;  // ← FALSE fixes duplicates
//     voiceRecognition.lang           = 'en-AU';

//     voiceRecognition.onresult = e => {
//         // Only final results — no interim accumulation
//         for (let i = e.resultIndex; i < e.results.length; i++) {
//             if (e.results[i].isFinal) {
//                 voiceText += e.results[i][0].transcript + ' ';
//             }
//         }

//         const voiceTextEl = document.getElementById('voice-text');
//         if (voiceTextEl) {
//             voiceTextEl.textContent = voiceText.trim() || 'Listening...';
//         }
//     };

//     voiceRecognition.onend = () => {
//         isRecording = false;
//         updateVoiceUI(false);

//         if (voiceText.trim()) {
//             const mode = getCurrentMode();
//             if (mode === 'gut') {
//                 document.getElementById('gut-analyze-voice-btn')
//                         .style.display = 'block';
//                 document.getElementById('analyze-voice-btn')
//                         .style.display = 'none';
//             } else {
//                 document.getElementById('analyze-voice-btn')
//                         .style.display = 'block';
//                 document.getElementById('gut-analyze-voice-btn')
//                         .style.display = 'none';
//             }
//         }
//     };

//     voiceRecognition.onerror = e => {
//         isRecording = false;
//         updateVoiceUI(false);
//         if (e.error !== 'no-speech') {
//             alert('Voice error: ' + e.error);
//         }
//     };

//     updateVoiceUI(true);
//     voiceRecognition.start();
//     isRecording = true;
// }


function stopVoice() { if (voiceRecognition) voiceRecognition.stop(); isRecording = false; updateVoiceUI(false); }

async function analyzeVoice() {
    updateVoiceUI(false);
    if (!voiceText) { showError('Please speak your meal description first.'); return; }

    // Route to gut analysis if in gut mode
    if (getCurrentMode() === 'gut') {
        gutAnalyzeVoice(voiceText); return;
    }

    clearError();
    showLoading(true);
    document.getElementById('analyze-voice-btn').style.display = 'none';
    document.getElementById('results').style.display           = 'none';
    try {
        const res  = await fetch('/analyze-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: voiceText, provider: getSelectedProvider(),
                timezone: getUserTimezone()
            })
        });
        const data = await res.json();
        if (data.error) { showError('Error: ' + data.error); }
        else { showResults(data); }
    } catch (err) {
        showError('Something went wrong: ' + err.message);
    } finally {
        showLoading(false);
    }
}

// ── Show results ──────────────────────────────────
function showResults(data) {
    clearError();
    document.getElementById('meal-description').textContent = data.meal_description;

    // Store for confirmation
    currentMealTimestamp = data.timestamp     || null;
    currentCuisineType   = data.cuisine_type  || '';
    currentGutScore      = data.overall_gut_health_score || 0;
    currentGutNotes      = data.overall_gut_notes        || '';

    try {
        const dbg = document.getElementById('debug-log');
        if (data.debug_log && data.debug_log.length) {
            dbg.textContent    = data.debug_log.join('\n');
            dbg.style.display  = 'block';
        } else {
            dbg.textContent    = '';
            dbg.style.display  = 'none';
        }
    } catch (e) { /* ignore */ }

    currentResults = data.foods.map(f => {
        const grams  = Number(f.grams) || 0;
        const per100 = {
            energy_kcal:   grams ? (Number(f.calories)    || 0) * 100 / grams : 0,
            protein:       grams ? (Number(f.protein)     || 0) * 100 / grams : 0,
            carbohydrates: grams ? (Number(f.carbs)       || 0) * 100 / grams : 0,
            fat:           grams ? (Number(f.fat)         || 0) * 100 / grams : 0,
            fibre:         grams ? (Number(f.fibre)       || 0) * 100 / grams : 0,
            sugars:        grams ? (Number(f.sugars)      || 0) * 100 / grams : 0,
            sodium:        grams ? (Number(f.sodium)      || 0) * 100 / grams : 0,
            calcium:       grams ? (Number(f.calcium)     || 0) * 100 / grams : 0,
            iron:          grams ? (Number(f.iron)        || 0) * 100 / grams : 0,
            magnesium:     grams ? (Number(f.magnesium)   || 0) * 100 / grams : 0,
            potassium:     grams ? (Number(f.potassium)   || 0) * 100 / grams : 0,
            zinc:          grams ? (Number(f.zinc)        || 0) * 100 / grams : 0,
            vitamin_a:     grams ? (Number(f.vitamin_a)   || 0) * 100 / grams : 0,
            vitamin_c:     grams ? (Number(f.vitamin_c)   || 0) * 100 / grams : 0,
            vitamin_d:     grams ? (Number(f.vitamin_d)   || 0) * 100 / grams : 0,
            vitamin_e:     grams ? (Number(f.vitamin_e)   || 0) * 100 / grams : 0,
            cholesterol:   grams ? (Number(f.cholesterol) || 0) * 100 / grams : 0
        };
        return calculateRowNutrition({ ...f, grams, per100 });
    });

    renderResultRows();
    document.getElementById('results').style.display = 'block';
    document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

// ── Confirm / Retake ──────────────────────────────
async function confirmResults() {
    try {
        const mealData = {
            meal_description:         document.getElementById('meal-description').textContent,
            foods:                    currentResults,
            total_calories:           currentResults.reduce((s, f) => s + (f.calories || 0), 0),
            timestamp:                currentMealTimestamp,
            cuisine_type:             currentCuisineType,
            overall_gut_health_score: currentGutScore,
            overall_gut_notes:        currentGutNotes,
            timezone:                 getUserTimezone()
        };
        const res    = await fetch('/confirm-meal', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(mealData)
        });
        const result = await res.json();
        if (result.error) { showError('Failed to save: ' + result.error); return; }
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
    currentResults = [];
    document.getElementById('results').style.display = 'none';
    window.scrollTo({ top: 0, behavior: 'smooth' });
    document.querySelector('.tab')?.click();
    resetApp();
}

// ── History ───────────────────────────────────────
function shiftHistoryDate(delta) {
    historyDateOffset += delta;
    if (historyDateOffset > 0) historyDateOffset = 0;
    loadHistory();
}

function refreshHistory() {
    const btn = document.querySelector('.date-nav-refresh');
    if (btn) btn.classList.add('spinning');
    loadHistory().finally(() => {
        if (btn) btn.classList.remove('spinning');
    });
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
        labelEl.textContent = d.toLocaleDateString(undefined, { weekday: 'long' });
    }
    if (subEl)   subEl.textContent   = getHistoryDate(historyDateOffset);
    if (nextBtn) nextBtn.disabled     = historyDateOffset >= 0;
}

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
        const targetDate  = getHistoryDate(historyDateOffset);
        const isToday     = historyDateOffset === 0;
        const fetches     = [
            fetch(`/history/daily?date=${targetDate}`),
            fetch('/history')
        ];
        if (isToday) fetches.push(loadFitnessData());

        const results     = await Promise.all(fetches);
        const daily       = await results[0].json();
        const all         = await results[1].json();
        const fitnessData = isToday ? results[2] : null;

        if (daily.error) {
            container.innerHTML = `<p class="hint" style="padding:16px">
                Error: ${daily.error}</p>`;
            return;
        }

        container.innerHTML = [
            isToday ? buildFitnessPanel(fitnessData) : '',
            buildDailyGaps(daily),
            buildTimeline(daily),
            buildPastMeals(all, targetDate)
        ].filter(Boolean).join('');

    } catch (e) {
        container.innerHTML = `<p class="hint" style="padding:16px">
            Could not load: ${e.message}</p>`;
    }
}

// ── Fitness ───────────────────────────────────────
async function loadFitnessData() {
    try {
        const res  = await fetch('/fitness');
        const data = await res.json();
        if (data.error) return null;
        return data;
    } catch (e) { return null; }
}

// ── History UI builders ───────────────────────────
const REC_TYPE_META = {
    activity:    { accent: 'rec-activity',    badge: 'Activity'  },
    timing:      { accent: 'rec-timing',      badge: 'Right Now' },
    meal_timing: { accent: 'rec-meal-timing', badge: 'Meal Plan' },
    nutrient:    { accent: 'rec-nutrient',    badge: 'Nutrition' },
    reminder:    { accent: 'rec-reminder',    badge: 'Reminder'  },
    calorie:     { accent: 'rec-nutrient',    badge: 'Calories'  },
};
const PRIORITY_DOT = {
    high:    '<span class="rec-dot dot-high"></span>',
    medium:  '<span class="rec-dot dot-medium"></span>',
    caution: '<span class="rec-dot dot-caution"></span>',
    low:     '<span class="rec-dot dot-low"></span>',
};

function buildRecCard(r) {
    const meta    = REC_TYPE_META[r.type] || REC_TYPE_META.nutrient;
    const dot     = PRIORITY_DOT[r.priority] || PRIORITY_DOT.low;
    const isMeal  = r.type === 'meal_timing';
    const actions = r.actions || [];
    const actHtml = actions.length === 0 ? '' :
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
                ${actHtml}
            </div>
        </div>`;
}

function buildFitnessPanel(data) {
    if (!data) return '';
    const fit  = data.fitness         || {};
    const recs = data.recommendations || {};
    const statsHtml = fit.available ? `
        <div class="fitness-stats-row">
            <div class="fitness-stat">
                <span class="fitness-stat-val">${(fit.steps||0).toLocaleString()}</span>
                <span class="fitness-stat-lbl">Steps</span>
            </div>
            <div class="fitness-stat">
                <span class="fitness-stat-val">${fit.calories_burned||0}</span>
                <span class="fitness-stat-lbl">kcal Active</span>
            </div>
            <div class="fitness-stat">
                <span class="fitness-stat-val">${fit.activity_emoji||'—'}</span>
                <span class="fitness-stat-lbl">${fit.activity_label||'Unknown'}</span>
            </div>
        </div>
        <div class="fitness-calorie-bar">
            <div class="fitness-calorie-row">
                <span>🍽️ Consumed</span>
                <span class="fitness-cal-num">${recs.cal_consumed||0} kcal</span>
            </div>
            <div class="fitness-calorie-row">
                <span>🔥 Active Burn</span>
                <span class="fitness-cal-num">${fit.calories_burned||0} kcal</span>
            </div>
            <div class="fitness-calorie-divider"></div>
            <div class="fitness-calorie-row fitness-calorie-remaining">
                <span>⚡ Remaining</span>
                <span class="fitness-cal-num ${(recs.cal_remaining||0)<0?'cal-over':'cal-ok'}">
                    ${(recs.cal_remaining||0)>=0
                        ? `${recs.cal_remaining} kcal to go`
                        : `${Math.abs(recs.cal_remaining)} kcal over`}
                </span>
            </div>
        </div>` : `
        <div class="fitness-unavailable">
            <span>📱</span>
            <span>Connect Google Fit to see activity data</span>
        </div>`;
    const recsHtml = (recs.recommendations||[]).map(r => buildRecCard(r)).join('');
    return `
        <div class="fitness-card">
            <div class="gap-card-title">🏃 Activity & Smart Recommendations</div>
            ${statsHtml}
        </div>
        ${recsHtml ? `
            <div class="recs-section">
                <div class="recs-section-label">💡 Personalised Recommendations</div>
                ${recsHtml}
            </div>` : ''}`;
}

function buildDailyGaps(daily) {
    const gaps    = daily.gaps         || [];
    const totals  = daily.daily_totals || {};
    const targets = daily.daily_targets|| {};
    if (!gaps.length) {
        return `<div class="gap-card gap-card-empty">
            <div class="gap-card-title">📊 Today's Nutrition</div>
            <p class="hint">No meals logged today yet.</p>
        </div>`;
    }
    const macros = ['calories','protein','carbs','fat','fibre'];
    const macroLabels = { calories:'Calories', protein:'Protein', carbs:'Carbs', fat:'Fat', fibre:'Fibre' };
    const macroUnits  = { calories:'kcal', protein:'g', carbs:'g', fat:'g', fibre:'g' };
    const progressBars = macros.map(key => {
        const consumed = totals[key]  || 0;
        const target   = targets[key] || 1;
        const pct      = Math.min(100, Math.round(consumed / target * 100));
        const color    = pct >= 90 ? '#2d8f58' : pct >= 60 ? '#e8762a' : '#dc2626';
        return `
            <div class="macro-progress-row">
                <div class="macro-progress-label">
                    <span>${macroLabels[key]}</span>
                    <span class="macro-progress-val">
                        ${Math.round(consumed)} / ${target} ${macroUnits[key]}
                    </span>
                </div>
                <div class="macro-progress-bar-bg">
                    <div class="macro-progress-bar-fill"
                         style="width:${pct}%;background:${color}"></div>
                </div>
            </div>`;
    }).join('');
    const alerts    = gaps.filter(g => g.severity !== 'good');
    const alertsHtml = alerts.length ? alerts.map(a => `
        <div class="gap-alert gap-alert-${a.severity}">
            <span class="gap-alert-icon">${severityIcon(a.severity)}</span>
            <div>
                <strong>${a.label}</strong>
                ${a.consumed > 0
                    ? `<span class="gap-alert-nums">
                           ${a.consumed}${a.unit} / ${a.target}${a.unit} (${a.pct}%)
                       </span>` : ''}
                <p class="gap-alert-msg">${a.message}</p>
            </div>
        </div>`).join('')
        : '<p class="hint" style="margin-top:8px">✅ All nutrients on track today!</p>';
    return `
        <div class="gap-card">
            <div class="gap-card-title">📊 Today's Progress — ${daily.date}</div>
            <div class="gap-meal-count">
                ${daily.meal_count} meal${daily.meal_count !== 1 ? 's' : ''} logged
            </div>
            <div class="macro-progress-stack">${progressBars}</div>
            <div class="gap-alerts-section">
                <div class="gap-alerts-title">⚡ Nutrition Alerts</div>
                ${alertsHtml}
            </div>
        </div>`;
}

function severityIcon(s) {
    if (s === 'high')    return '🔴';
    if (s === 'medium')  return '🟠';
    if (s === 'warning') return '⚠️';
    if (s === 'caution') return '🟡';
    return '✅';
}

function buildTimeline(daily) {
    const timeline = daily.timeline || [];
    if (!timeline.length) return '';
    const icons = {
        'Breakfast':'🌅','Morning Snack':'☕','Lunch':'☀️',
        'Afternoon Snack':'🍎','Dinner':'🌙','Late Snack':'🌚'
    };
    const sections = timeline.map(cat => {
        const icon  = icons[cat.category] || '🍽️';
        const meals = cat.meals.map(meal => `
            <div class="timeline-meal">
                <div class="timeline-meal-time">
                    ${meal.timestamp ? meal.timestamp.slice(11,16) : ''}
                </div>
                <div class="timeline-meal-body">
                    <div class="timeline-meal-desc">
                        ${meal.meal_description || 'Meal'}
                    </div>
                    <div class="timeline-meal-foods">
                        ${(meal.foods||[]).map(f=>`${f.name} (${f.grams}g)`).join(' · ')}
                    </div>
                    <div class="timeline-meal-cal">
                        🔥 ${meal.total_calories || 0} kcal
                    </div>
                </div>
            </div>`).join('');
        const t = cat.totals;
        return `
            <div class="timeline-section">
                <div class="timeline-section-header">
                    <span class="timeline-icon">${icon}</span>
                    <span class="timeline-cat-name">${cat.category}</span>
                    <span class="timeline-cat-cal">
                        ${Math.round(t.calories||0)} kcal
                    </span>
                </div>
                <div class="timeline-meals">${meals}</div>
                <div class="timeline-section-totals">
                    P: ${(t.protein||0).toFixed(1)}g &nbsp;|&nbsp;
                    C: ${(t.carbs||0).toFixed(1)}g &nbsp;|&nbsp;
                    F: ${(t.fat||0).toFixed(1)}g &nbsp;|&nbsp;
                    Fibre: ${(t.fibre||0).toFixed(1)}g
                </div>
            </div>`;
    }).join('');
    return `
        <div class="timeline-card">
            <div class="gap-card-title">🕐 Today's Timeline</div>
            ${sections}
        </div>`;
}

function buildPastMeals(all, today) {
    const past = [...all].reverse()
        .filter(m => !m.timestamp || !m.timestamp.startsWith(today))
        .slice(0, 10);
    if (!past.length) return '';
    const items = past.map(m => `
        <div class="history-item">
            <div class="history-date">
                📅 ${m.timestamp||''} · ${m.meal_category||'Meal'}
            </div>
            <div class="history-desc">${m.meal_description||'Meal'}</div>
            <div class="history-foods">
                ${(m.foods||[]).map(f=>`${f.name} (${f.grams}g)`).join(' · ')}
            </div>
            <div class="history-meta">
                <span class="history-cal">
                    🔥 ${m.total_calories||0} kcal
                </span>
            </div>
        </div>`).join('');
    return `
        <div class="card" style="margin-top:12px">
            <div class="card-label">📆 Previous Meals</div>
            ${items}
        </div>`;
}

// ── Helpers ───────────────────────────────────────
function showLoading(show) {
    const el = document.getElementById('loading');
    if (el) el.style.display = show ? 'block' : 'none';
}

function resetApp() {
    currentImageBase64 = null;
    voiceText          = '';
    clearError();

    const safe = (id, prop, val) => {
        const el = document.getElementById(id);
        if (el) el[prop] = val;
    };

    safe('photo-preview',       'style.display', 'none');
    safe('camera-preview',      'style.display', 'none');
    safe('camera-placeholder',  'style.display', 'block');
    safe('capture-btn',         'style.display', 'none');
    clearPhoto();
    safe('results',             'style.display', 'none');
    safe('voice-text',          'textContent',   '');

    hideAllAnalyzeButtons();
    enableOpenAIOption();
}

// ── Mode selector ─────────────────────────────────
function initModeSelector() {
    const radios    = document.querySelectorAll('input[name="app-mode"]');
    const savedMode = localStorage.getItem('appMode') || 'health';
    const radio     = document.querySelector(`input[value="${savedMode}"]`);
    if (radio) radio.checked = true;
    applyMode(savedMode);
    radios.forEach(r => {
        r.addEventListener('change', e => applyMode(e.target.value));
    });
}

function applyMode(mode) {
    const healthContent = document.getElementById('health-mode-content');
    const gutContent    = document.getElementById('gut-mode-content');

    if (mode === 'gut') {
        if (healthContent) healthContent.style.display = 'none';
        if (gutContent)    gutContent.style.display    = 'block';
        // If image already loaded swap buttons
        if (currentImageBase64) showCorrectAnalyzeButton();
        if (!window.gutAppLoaded) loadGutApp();
    } else {
        if (healthContent) healthContent.style.display = 'block';
        if (gutContent)    gutContent.style.display    = 'none';
        // If image already loaded swap buttons
        if (currentImageBase64) showCorrectAnalyzeButton();
    }

    localStorage.setItem('appMode', mode);
}

function loadGutApp() {
    const script   = document.createElement('script');
    script.src     = '/static/js/gut_app.js';
    script.onload  = () => {
        window.gutAppLoaded = true;
        if (typeof initGutMode === 'function') initGutMode();
    };
    document.head.appendChild(script);
}

// ── PWA ───────────────────────────────────────────
let deferredPrompt;
window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    deferredPrompt = e;
});


document.addEventListener('DOMContentLoaded', initModeSelector);



function openCameraOverlay() {
    const overlay = document.getElementById('camera-overlay');
    if (overlay) {
        overlay.style.display = 'flex';
        overlay.style.flexDirection = 'column';
    }
    // Auto-start camera immediately
    startCamera();
}

function closeCameraOverlay() {
    const overlay = document.getElementById('camera-overlay');
    if (overlay) overlay.style.display = 'none';
    const video = document.getElementById('camera-preview');
    if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(t => t.stop());
        video.srcObject = null;
        video.style.display = 'none';
    }
    const captureBtn = document.getElementById('capture-btn');
    if (captureBtn) captureBtn.style.display = 'none';
    const placeholder = document.getElementById('camera-placeholder');
    if (placeholder) placeholder.style.display = 'flex';
    const preview = document.getElementById('photo-preview');
    if (preview) preview.style.display = 'none';
}

function updateVoiceUI(isRecording) {
    const voiceBtn  = document.getElementById('voice-action-btn');
    const recordBar = document.getElementById('voice-recording-bar');
    const voiceTextEl = document.getElementById('voice-text');

    if (isRecording) {
        if (voiceBtn)    voiceBtn.classList.add('recording');
        if (recordBar)   recordBar.style.display = 'flex';
        if (voiceTextEl) voiceTextEl.textContent = 'Listening...';
    } else {
        if (voiceBtn)    voiceBtn.classList.remove('recording');
        if (recordBar)   recordBar.style.display = 'none';
    }
}