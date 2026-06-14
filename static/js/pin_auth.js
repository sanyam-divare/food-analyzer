// Override fetch globally to always send PIN header
const _originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    const pin = localStorage.getItem('food_analyzer_pin') || '';
    options.headers = {
        ...(options.headers || {}),
        'X-App-Pin': pin
    };
    return _originalFetch(url, options);
};

// ── PIN Authentication ────────────────────────────────────────────────────────
let currentPin     = '';
const PIN_STORAGE  = 'food_analyzer_pin';
const MAX_PIN_LEN  = 8;

// Called on page load — check if PIN already saved
async function initPinAuth() {
    const saved = localStorage.getItem(PIN_STORAGE);
    if (saved) {
        // Validate saved PIN is still valid (in case it was revoked)
        const ok = await validatePin(saved);
        if (ok) return; // Already authenticated
        localStorage.removeItem(PIN_STORAGE); // PIN revoked
    }
    showPinOverlay();
}

function showPinOverlay() {
    const overlay = document.getElementById('pin-overlay');
    if (overlay) overlay.style.display = 'flex';
    currentPin = '';
    updatePinDots();
}

function hidePinOverlay() {
    const overlay = document.getElementById('pin-overlay');
    if (overlay) overlay.style.display = 'none';
}

// Keypad button press
function pinKey(char) {
    if (currentPin.length >= MAX_PIN_LEN) return;
    currentPin += char;
    updatePinDots();
    hidePinError();
    if (currentPin.length === MAX_PIN_LEN) {
        // Auto-submit when max length reached
        setTimeout(submitPin, 200);
    }
}

function pinBackspace() {
    currentPin = currentPin.slice(0, -1);
    updatePinDots();
    hidePinError();
}

// Handle physical keyboard input
function onPinInput(val) {
    currentPin = val.toLowerCase();
    updatePinDots();
    hidePinError();
}

function onPinKey(e) {
    if (e.key === 'Enter') submitPin();
}

function updatePinDots() {
    const dots = document.querySelectorAll('.pin-dot');
    dots.forEach((dot, i) => {
        dot.classList.toggle('filled', i < currentPin.length);
    });
}

function showPinError() {
    const el = document.getElementById('pin-error');
    if (el) el.style.display = 'block';
    // Shake animation
    const modal = document.querySelector('.pin-modal');
    if (modal) {
        modal.classList.add('pin-shake');
        setTimeout(() => modal.classList.remove('pin-shake'), 500);
    }
    // Clear PIN
    currentPin = '';
    const input = document.getElementById('pin-input');
    if (input) input.value = '';
    updatePinDots();
}

function hidePinError() {
    const el = document.getElementById('pin-error');
    if (el) el.style.display = 'none';
}

// async function validatePin(pin) {
//     try {
//         const res  = await fetch('/auth/validate', {
//             method:  'POST',
//             headers: { 'Content-Type': 'application/json' },
//             body:    JSON.stringify({ pin: pin.toLowerCase() })
//         });
//         const data = await res.json();
//         if (data.valid) {
//             // Store patient_id globally
//             window.appPatientId = data.patient_id;
//             // Sync to gut tracker
//             if (typeof gutPatientId !== 'undefined') {
//                 gutPatientId = data.patient_id;
//             }
//             return true;
//         }
//         return false;
//     } catch {
//         return false;
//     }
// }

async function validatePin(pin) {
    try {
        const res  = await fetch('/auth/validate', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ pin: pin })
        });
        const data = await res.json();
        if (data.valid) {
            // Save both id and name
            localStorage.setItem('gut_patient_id',   data.patient_id);
            localStorage.setItem('gut_patient_name',  data.name);
            localStorage.setItem(PIN_STORAGE,         pin);

            window.appPatientId = data.patient_id;
            window.appPatientName = data.name;

            if (typeof gutPatientId !== 'undefined') {
                gutPatientId = data.patient_id;
            }
            return true;
        }
        return false;
    } catch (e) {
        console.error('PIN validation error:', e);
        return false;
    }
}

async function submitPin() {
    if (!currentPin) return;
    const pin = currentPin.toLowerCase();

    // Show loading state
    const keypad = document.querySelector('.pin-keypad');
    if (keypad) keypad.style.opacity = '0.5';

    const ok = await validatePin(pin);

    if (keypad) keypad.style.opacity = '1';

    if (ok) {
        // Save PIN so user doesn't need to re-enter
        localStorage.setItem(PIN_STORAGE, pin);
        hidePinOverlay();
        // Reinitialise app with correct patient_id
        if (typeof initApp === 'function') initApp();
    } else {
        showPinError();
    }
}
window.addEventListener('DOMContentLoaded', async () => {
    await initPinAuth();
});
// Call initPinAuth() when page loads
// Add this to your existing window.onload or DOMContentLoaded