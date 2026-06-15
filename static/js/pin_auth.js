// Override fetch globally to always send PIN header
const _originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    // Read PIN from multiple sources — whichever is available
    const pin = localStorage.getItem('food_analyzer_pin')
             || window._currentPin
             || '';
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
    const saved = localStorage.getItem('food_analyzer_pin');
    if (saved) {
        // Restore to memory immediately
        window._currentPin = saved;

        const ok = await validatePin(saved);
        if (ok) return;
        localStorage.removeItem('food_analyzer_pin');
        window._currentPin = null;
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

// // Temporary visual debug
// const debugDiv = document.createElement('div');
// debugDiv.style.cssText = 'position:fixed;top:0;left:0;right:0;background:red;color:white;padding:10px;z-index:9999;font-size:12px';
// debugDiv.innerHTML = `
//     PIN: ${localStorage.getItem('food_analyzer_pin')}<br>
//     patient_id: ${localStorage.getItem('gut_patient_id')}<br>
//     patient_name: ${localStorage.getItem('gut_patient_name')}<br>
//     gutPatientId: ${typeof gutPatientId !== 'undefined' ? gutPatientId : 'UNDEFINED'}
// `;
// document.body.appendChild(debugDiv);
// setTimeout(() => debugDiv.remove(), 5000);


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
            // Save to memory FIRST (instant)
            window._currentPin = pin;

            // Then save to localStorage
            localStorage.setItem('food_analyzer_pin',  pin);
            localStorage.setItem('gut_patient_id',     data.patient_id);
            localStorage.setItem('gut_patient_name',   data.name);

            window.appPatientId  = data.patient_id;
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

// async function submitPin() {
//     if (!currentPin) return;
//     const pin = currentPin.toLowerCase();

//     // Show loading state
//     const keypad = document.querySelector('.pin-keypad');
//     if (keypad) keypad.style.opacity = '0.5';

//     const ok = await validatePin(pin);

//     if (keypad) keypad.style.opacity = '1';

//     if (ok) {
//         localStorage.setItem(PIN_STORAGE, pin);
//         hidePinOverlay();

//         // DEBUG — check what's stored
//         console.log('PIN stored:', localStorage.getItem('food_analyzer_pin'));
//         console.log('patient_id stored:', localStorage.getItem('gut_patient_id'));
//         console.log('patient_name stored:', localStorage.getItem('gut_patient_name'));
//         console.log('gutPatientId var:', typeof gutPatientId !== 'undefined' ? gutPatientId : 'undefined');

//         if (typeof syncPatientFromStorage === 'function') {
//             syncPatientFromStorage();
//             console.log('After sync - gutPatientId:', gutPatientId);
//         }
//         if (typeof renderGutDashboard === 'function') {
//             renderGutDashboard();
//         }
//         if (typeof gutProfileLoaded !== 'undefined') {
//             gutProfileLoaded = false;
//         }
//     }
    
//     else {
//         showPinError();
//     }
// }

async function submitPin() {
    if (!currentPin) return;
    const pin = currentPin.toLowerCase();

    const keypad = document.querySelector('.pin-keypad');
    if (keypad) keypad.style.opacity = '0.5';

    const ok = await validatePin(pin);

    if (keypad) keypad.style.opacity = '1';

    if (ok) {
        localStorage.setItem(PIN_STORAGE, pin);
        hidePinOverlay();

        // Let gut_app.js handle everything
        // It reads from localStorage which is now updated
        if (typeof onPinSuccess === 'function') {
            onPinSuccess();
        }
    } else {
        showPinError();
    }
}

window.addEventListener('DOMContentLoaded', async () => {
    await initPinAuth();
});
// Call initPinAuth() when page loads
// Add this to your existing window.onload or DOMContentLoaded