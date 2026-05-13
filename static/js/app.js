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

    // Stop camera stream
    video.srcObject.getTracks().forEach(t => t.stop());
    video.style.display = 'none';

    // Show preview
    const imageData = canvas.toDataURL('image/jpeg', 0.8);
    const preview = document.getElementById('photo-preview');
    preview.src = imageData;
    preview.style.display = 'block';

    // Store base64
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
        const preview = document.getElementById('photo-preview');
        preview.src = imageData;
        preview.style.display = 'block';
        document.getElementById('camera-preview').style.display = 'none';
        currentImageBase64 = imageData.split(',')[1];
        document.getElementById('analyze-btn').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// ── Analyze Photo ────────────────────────────────
async function analyzePhoto() {
    if (!currentImageBase64) {
        alert('Please take or upload a photo first!');
        return;
    }

    showLoading(true);
    document.getElementById('analyze-btn').style.display = 'none';
    document.getElementById('results').style.display = 'none';

    try {
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image: currentImageBase64,
                mime_type: currentMimeType
            })
        });

        const data = await response.json();
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            showResults(data);
        }
    } catch (err) {
        alert('Something went wrong. Please try again.');
    } finally {
        showLoading(false);
    }
}

// ── Voice Input ──────────────────────────────────
function toggleVoice() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert('Voice input not supported in this browser. Try Chrome or Samsung Browser.');
        return;
    }

    if (isRecording) {
        stopVoice();
    } else {
        startVoice();
    }
}

function startVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    voiceRecognition = new SpeechRecognition();
    voiceRecognition.continuous = false;
    voiceRecognition.interimResults = true;
    voiceRecognition.lang = 'en-US';

    voiceRecognition.onresult = (event) => {
        const transcript = Array.from(event.results)
            .map(r => r[0].transcript)
            .join('');
        document.getElementById('voice-text').textContent = transcript;
        voiceText = transcript;
    };

    voiceRecognition.onend = () => {
        isRecording = false;
        const btn = document.getElementById('voice-btn');
        btn.textContent = '🎤 Tap to Speak';
        btn.classList.remove('recording');
        if (voiceText) {
            document.getElementById('analyze-voice-btn').style.display = 'block';
        }
    };

    voiceRecognition.onerror = (event) => {
        isRecording = false;
        document.getElementById('voice-btn').classList.remove('recording');
        alert('Voice error: ' + event.error);
    };

    voiceRecognition.start();
    isRecording = true;
    const btn = document.getElementById('voice-btn');
    btn.textContent = '⏹️ Stop Recording';
    btn.classList.add('recording');
}

function stopVoice() {
    if (voiceRecognition) voiceRecognition.stop();
}

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
        if (data.error) {
            alert('Error: ' + data.error);
        } else {
            showResults(data);
        }
    } catch (err) {
        alert('Something went wrong. Please try again.');
    } finally {
        showLoading(false);
    }
}

// ── Show Results ─────────────────────────────────
function showResults(data) {
    document.getElementById('meal-description').textContent = data.meal_description;
    document.getElementById('total-cal').textContent = data.total_calories + ' kcal';

    // Calculate totals
    let totalProtein = 0, totalCarbs = 0, totalFat = 0;
    data.foods.forEach(f => {
        totalProtein += f.protein;
        totalCarbs += f.carbs;
        totalFat += f.fat;
    });

    document.getElementById('total-protein').textContent = totalProtein.toFixed(1) + 'g';
    document.getElementById('total-carbs').textContent = totalCarbs.toFixed(1) + 'g';
    document.getElementById('total-fat').textContent = totalFat.toFixed(1) + 'g';

    // Food list
    const foodsList = document.getElementById('foods-list');
    foodsList.innerHTML = data.foods.map(food => `
        <div class="food-item">
            <div>
                <div class="food-name">${food.name}</div>
                <div class="food-grams">${food.grams}g
                    ${!food.found_in_db ? '<span class="food-not-found">not in DB</span>' : ''}
                </div>
            </div>
            <div class="food-calories">${food.calories} kcal</div>
        </div>
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
    document.getElementById('photo-preview').style.display = 'none';
    document.getElementById('camera-preview').style.display = 'none';
    document.getElementById('analyze-btn').style.display = 'none';
    document.getElementById('analyze-voice-btn').style.display = 'none';
    document.getElementById('results').style.display = 'none';
    document.getElementById('voice-text').textContent = '';
    document.getElementById('capture-btn').style.display = 'none';
}

// ── PWA Install ──────────────────────────────────
let deferredPrompt;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
});