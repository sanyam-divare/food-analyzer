// ── State ───────────────────────────────────────
let currentImageBase64 = null;
let currentMimeType = 'image/jpeg';
let voiceRecognition = null;
let isRecording = false;
let voiceText = '';

// ── Tabs ────────────────────────────────────────
function showTab(tab) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    event.target.classList.add('active');
    if (tab === 'history') loadHistory();
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
    const reader = new FileReader();
    reader.onload = (e) => {
        const imageData = e.target.result;
        document.getElementById('photo-preview').src = imageData;
        document.getElementById('photo-preview').style.display = 'block';
        document.getElementById('camera-preview').style.display = 'none';
        document.getElementById('camera-placeholder').style.display = 'none';
        currentImageBase64 = imageData.split(',')[1];
        document.getElementById('analyze-btn').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// ── Analyze Photo ────────────────────────────────
async function analyzePhoto() {
    if (!currentImageBase64) { alert('Please take or upload a photo first!'); return; }
    showLoading(true);
    document.getElementById('analyze-btn').style.display = 'none';
    document.getElementById('results').style.display = 'none';
    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: currentImageBase64, mime_type: currentMimeType })
        });
        const data = await response.json();
        if (data.error) { alert('Error: ' + data.error); }
        else { showResults(data); }
    } catch (err) {
        alert('Something went wrong: ' + err.message);
    } finally { showLoading(false); }
}

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
    if (!voiceText) return;
    showLoading(true);
    document.getElementById('analyze-voice-btn').style.display = 'none';
    document.getElementById('results').style.display = 'none';
    try {
        const response = await fetch('/analyze-voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: voiceText })
        });
        const data = await response.json();
        if (data.error) { alert('Error: ' + data.error); }
        else { showResults(data); }
    } catch (err) {
        alert('Something went wrong: ' + err.message);
    } finally { showLoading(false); }
}

// ── Show Results ─────────────────────────────────
function showResults(data) {
    document.getElementById('meal-description').textContent = data.meal_description;

    // Totals
    let totals = {
        cal:0, protein:0, carbs:0, fat:0, fibre:0, sugars:0,
        sodium:0, calcium:0, iron:0, magnesium:0, potassium:0,
        zinc:0, vitamin_a:0, vitamin_c:0, vitamin_d:0, vitamin_e:0, cholesterol:0
    };

    data.foods.forEach(f => {
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

    // Macro summary cards
    document.getElementById('summary-cal').textContent     = Math.round(totals.cal) + ' kcal';
    document.getElementById('summary-protein').textContent = totals.protein.toFixed(1) + 'g';
    document.getElementById('summary-carbs').textContent   = totals.carbs.toFixed(1) + 'g';
    document.getElementById('summary-fat').textContent     = totals.fat.toFixed(1) + 'g';

    // Macro table totals
    document.getElementById('total-cal').textContent      = Math.round(totals.cal);
    document.getElementById('total-protein').textContent  = totals.protein.toFixed(1) + 'g';
    document.getElementById('total-carbs').textContent    = totals.carbs.toFixed(1) + 'g';
    document.getElementById('total-sugars').textContent   = totals.sugars.toFixed(1) + 'g';
    document.getElementById('total-fat').textContent      = totals.fat.toFixed(1) + 'g';
    document.getElementById('total-fibre').textContent    = totals.fibre.toFixed(1) + 'g';

    // Micro table totals
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

    // Macro table rows
    document.getElementById('foods-list').innerHTML = data.foods.map(f => `
        <tr>
            <td>
                ${f.name}
                ${f.matched && f.matched !== f.name ?
                    `<div style="font-size:0.7rem;color:var(--gray-400)">${f.matched}</div>` : ''}
                ${!f.found_in_db ? '<span class="not-in-db">not in DB</span>' : ''}
            </td>
            <td>${f.grams}g</td>
            <td class="kcal-cell">${(f.calories||0).toFixed(0)}</td>
            <td>${(f.protein||0).toFixed(1)}g</td>
            <td>${(f.carbs||0).toFixed(1)}g</td>
            <td>${(f.sugars||0).toFixed(1)}g</td>
            <td>${(f.fat||0).toFixed(1)}g</td>
            <td>${(f.fibre||0).toFixed(1)}g</td>
        </tr>
    `).join('');

    // Micro table rows
    document.getElementById('micro-list').innerHTML = data.foods.map(f => `
        <tr>
            <td>${f.name.length > 20 ? f.name.substring(0,20)+'…' : f.name}</td>
            <td>${(f.sodium||0).toFixed(1)}</td>
            <td>${(f.calcium||0).toFixed(1)}</td>
            <td>${(f.iron||0).toFixed(2)}</td>
            <td>${(f.magnesium||0).toFixed(1)}</td>
            <td>${(f.potassium||0).toFixed(1)}</td>
            <td>${(f.zinc||0).toFixed(2)}</td>
            <td>${(f.vitamin_a||0).toFixed(1)}</td>
            <td>${(f.vitamin_c||0).toFixed(1)}</td>
            <td>${(f.vitamin_d||0).toFixed(2)}</td>
            <td>${(f.vitamin_e||0).toFixed(2)}</td>
            <td>${(f.cholesterol||0).toFixed(1)}</td>
        </tr>
    `).join('');

    document.getElementById('results').style.display = 'block';
    document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
}

// ── History ──────────────────────────────────────
async function loadHistory() {
    try {
        const response = await fetch('/history');
        const data = await response.json();
        const container = document.getElementById('history-list');
        if (data.length === 0) {
            container.innerHTML = '<p class="hint">No meals logged yet!</p>';
            return;
        }
        container.innerHTML = data.reverse().map(meal => `
            <div class="history-item">
                <div class="history-date">📅 ${meal.timestamp}</div>
                <div class="history-desc">${meal.meal_description}</div>
                <div class="history-foods">${meal.foods.map(f => `${f.name} (${f.grams}g)`).join(' · ')}</div>
                <div class="history-cal">🔥 ${meal.total_calories} kcal</div>
            </div>
        `).join('');
    } catch (err) {
        document.getElementById('history-list').innerHTML = '<p class="hint">Could not load history.</p>';
    }
}

// ── Helpers ──────────────────────────────────────
function showLoading(show) {
    document.getElementById('loading').style.display = show ? 'block' : 'none';
}

function resetApp() {
    currentImageBase64 = null;
    voiceText = '';
    document.getElementById('photo-preview').style.display     = 'none';
    document.getElementById('camera-preview').style.display    = 'none';
    document.getElementById('camera-placeholder').style.display = 'block';
    document.getElementById('analyze-btn').style.display       = 'none';
    document.getElementById('analyze-voice-btn').style.display = 'none';
    document.getElementById('results').style.display           = 'none';
    document.getElementById('voice-text').textContent          = '';
    document.getElementById('capture-btn').style.display       = 'none';
}

// ── PWA ──────────────────────────────────────────
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
});
