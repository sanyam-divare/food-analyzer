// ══════════════════════════════════════════════════════════════════════════════
// gut_app.js  —  Gut Health Tracker (Persona 2)
// ══════════════════════════════════════════════════════════════════════════════

let gutCurrentResults = null;
let gutMealTimestamp  = null;
let gutPatientId      = localStorage.getItem('gutPatientId') || 'guest';
let gutScorecardView  = 'daily';
let gutActiveTab      = 'scorecard';
let gutProfile        = null;
let gutDailyOffset = 0;  // 0 = today, -1 = yesterday, -2 = two days ago
let gutWeekOffset   = 0;  // 0 = current week, -1 = last week
let gutMonthOffset  = 0;
let gutDailyData = null;  // stores today's scorecard data

function initGutMode() {
    console.log('🦠 Gut mode initialised');
    renderGutDashboard();
}

function shiftDay(dir) {
    gutDailyOffset += dir;
    // Don't allow future dates
    if (gutDailyOffset > 0) gutDailyOffset = 0;
    loadGutScorecard();
}

function shiftWeek(dir) {
    gutWeekOffset += dir;
    loadGutScorecard();
}

function shiftMonth(dir) {
    gutMonthOffset += dir;
    loadGutScorecard();
}

function renderGutDashboard() {
    const container = document.getElementById('gut-mode-content');
    container.innerHTML = `
        <div class="card gut-header-card">
            <h2>🦠 Gut Health Tracker</h2>
            <div class="gut-disclaimer">
                ⚠️ AI-powered gut estimates. Validate with your practitioner.
            </div>
        </div>

        <div id="gut-results" style="display:none"></div>

        <div class="gut-tab-bar">
            <button class="gut-tab active"
                    onclick="showGutTab('scorecard',this)">
                <span class="gut-tab-icon">📊</span>
                <span class="gut-tab-label">Scorecard</span>
            </button>
            <button class="gut-tab"
                    onclick="showGutTab('plan',this)">
                <span class="gut-tab-icon">🥗</span>
                <span class="gut-tab-label">My Plan</span>
            </button>
            <button class="gut-tab"
                    onclick="showGutTab('history',this)">
                <span class="gut-tab-icon">📅</span>
                <span class="gut-tab-label">History</span>
            </button>
            <button class="gut-tab"
                    onclick="showGutTab('profile',this)">
                <span class="gut-tab-icon">⚙️</span>
                <span class="gut-tab-label">Profile</span>
            </button>
        </div>

        <div id="gut-tab-scorecard" class="gut-tab-panel">
            <div class="card">
                <div class="gut-scorecard-header">
                    <h2>📊 Gut Scorecard</h2>
                    <div class="scorecard-tabs">
                        <button class="scorecard-tab active"
                                onclick="switchScorecardView('daily',this)">Daily</button>
                        <button class="scorecard-tab"
                                onclick="switchScorecardView('weekly',this)">Weekly</button>
                        <button class="scorecard-tab"
                                onclick="switchScorecardView('monthly',this)">Monthly</button>
                    </div>
                </div>
                <div id="gut-scorecard"><p class="hint">Loading...</p></div>
            </div>
        </div>

        <div id="gut-tab-plan" class="gut-tab-panel" style="display:none">
            <div id="gut-plan-content">
                <p class="hint" style="padding:20px;text-align:center">Loading...</p>
            </div>
        </div>

        <div id="gut-tab-history" class="gut-tab-panel" style="display:none">
            <div class="card">
                <h2>📅 Gut Meal History</h2>
                <div id="gut-history-list">
                    <p class="hint">No gut meals logged yet.</p>
                </div>
            </div>
        </div>

        <div id="gut-tab-profile" class="gut-tab-panel" style="display:none">
            <div id="gut-profile-content">
                <p class="hint" style="padding:20px;text-align:center">Loading...</p>
            </div>
        </div>`;

    loadGutScorecard();
    loadGutHistory();
    loadGutProfile();
}

function showGutTab(tab, btn) {
    gutActiveTab = tab;
    document.querySelectorAll('.gut-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    ['scorecard','plan','history','profile'].forEach(t => {
        const panel = document.getElementById(`gut-tab-${t}`);
        if (panel) panel.style.display = t === tab ? 'block' : 'none';
    });
    if (tab === 'plan')    loadGutFoodPlan();
    if (tab === 'history') loadGutHistory();
}

// ── TAB 1: SCORECARD ─────────────────────────────────────────────────────────
function switchScorecardView(view, btn) {
    gutScorecardView = view;
    document.querySelectorAll('.scorecard-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    loadGutScorecard();
}

async function loadGutScorecard() {
    const container = document.getElementById('gut-scorecard');
    if (!container) return;
    container.innerHTML = `<div class="loading"><div class="spinner"></div><p>Loading...</p></div>`;

    try {
        // ── Build URL ──────────────────────────────────────────────────────
        let url = '';

        if (gutScorecardView === 'daily') {
            const now  = new Date();
            now.setDate(now.getDate() + gutDailyOffset);
            url = `/gut/scorecard/daily?patient_id=${gutPatientId}&date=${now.toLocaleDateString('en-CA')}`;

        } else if (gutScorecardView === 'weekly') {
            const now  = new Date();
            const from = new Date(now);
            from.setDate(now.getDate() - 6 + (gutWeekOffset * 7));
            url = `/gut/scorecard/weekly?patient_id=${gutPatientId}&week_start=${from.toLocaleDateString('en-CA')}&days=7`;

        } else {
            const now      = new Date();
            const rawMonth = now.getMonth() + 1 + gutMonthOffset;
            const adjYear  = now.getFullYear() + Math.floor((rawMonth - 1) / 12);
            const adjMonth = ((rawMonth - 1 + 120) % 12) + 1;
            url = `/gut/scorecard/monthly?patient_id=${gutPatientId}&year=${adjYear}&month=${adjMonth}`;
        }

        // ── Fetch ──────────────────────────────────────────────────────────
        const res  = await fetch(url);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<p class="hint">Error: ${data.error}</p>`;
            return;
        }

        // ── Render ─────────────────────────────────────────────────────────
        if (gutScorecardView === 'daily') {

            const navNow = new Date();
            navNow.setDate(navNow.getDate() + gutDailyOffset);
            const dateLabel = gutDailyOffset ===  0 ? 'Today'
                            : gutDailyOffset === -1 ? 'Yesterday'
                            : navNow.toLocaleDateString('en-AU', {
                                weekday: 'short',
                                day:     'numeric',
                                month:   'short'
                              });

            if (!data.meal_count || data.meal_count === 0) {
                container.innerHTML = `
                    <div style="text-align:center;padding:32px 16px">
                        <div style="font-size:2rem;margin-bottom:8px">🍽️</div>
                        <p class="hint">No meals logged ${
                            gutDailyOffset === 0 ? 'today' : 'on this day'
                        } yet.</p>
                        ${gutDailyOffset === 0
                            ? `<p class="hint" style="margin-top:6px">
                                   Log your first meal above!
                               </p>`
                            : ''}
                    </div>`;
            // } else {
            //     renderDailyScorecard(container, data);
            // }
            } else {
                // Clear summary cache before rendering new day
                const oldPanel = document.getElementById('day-summary-panel');
                if (oldPanel) oldPanel.innerHTML = '';
            
                renderDailyScorecard(container, data);
            }

            // Nav always added last — never gets wiped
            const nav = document.createElement('div');
            nav.className = 'scorecard-week-nav';
            nav.innerHTML = `
                <button onclick="shiftDay(-1)">← Prev</button>
                <span>${dateLabel}</span>
                <button onclick="shiftDay(1)"
                        ${gutDailyOffset >= 0
                            ? 'disabled style="opacity:.4"' : ''}>
                    Next →
                </button>`;
            container.insertBefore(nav, container.firstChild);

        } else if (gutScorecardView === 'weekly') {

            renderWeeklyScorecard(container, data);

            const now  = new Date();
            const from = new Date(now);
            const to   = new Date(now);
            from.setDate(now.getDate() - 6 + (gutWeekOffset * 7));
            to.setDate(now.getDate() + (gutWeekOffset * 7));
            const weekLabel = gutWeekOffset === 0
                ? 'Last 7 Days'
                : `${from.toLocaleDateString('en-AU', {day:'numeric',month:'short'})}–${to.toLocaleDateString('en-AU', {day:'numeric',month:'short'})}`;

            const nav = document.createElement('div');
            nav.className = 'scorecard-week-nav';
            nav.innerHTML = `
                <button onclick="shiftWeek(-1)">← Prev</button>
                <span>${weekLabel}</span>
                <button onclick="shiftWeek(1)"
                        ${gutWeekOffset >= 0
                            ? 'disabled style="opacity:.4"' : ''}>
                    Next →
                </button>`;
            container.insertBefore(nav, container.firstChild);

        } else {

            renderMonthlyScorecard(container, data);

            const now      = new Date();
            const rawMonth = now.getMonth() + 1 + gutMonthOffset;
            const adjYear  = now.getFullYear() + Math.floor((rawMonth - 1) / 12);
            const adjMonth = ((rawMonth - 1 + 120) % 12) + 1;
            const mNames   = ['Jan','Feb','Mar','Apr','May','Jun',
                              'Jul','Aug','Sep','Oct','Nov','Dec'];

            const nav = document.createElement('div');
            nav.className = 'scorecard-week-nav';
            nav.innerHTML = `
                <button onclick="shiftMonth(-1)">← Prev</button>
                <span>${mNames[adjMonth-1]} ${adjYear}</span>
                <button onclick="shiftMonth(1)"
                        ${gutMonthOffset >= 0
                            ? 'disabled style="opacity:.4"' : ''}>
                    Next →
                </button>`;
            container.insertBefore(nav, container.firstChild);
        }

    } catch (err) {
        container.innerHTML =
            `<p class="hint">Could not load: ${err.message}</p>`;
    }
}

async function fetchLastMealDate() {
    try {
        const res  = await fetch(`/gut/history?patient_id=${gutPatientId}`);
        const data = await res.json();
        if (!data.length) return null;
        const last = data[data.length - 1];
        return (last.timestamp || last.date || '').slice(0, 10);
    } catch {
        return null;
    }
}

// async function loadGutScorecard() {
//     const container = document.getElementById('gut-scorecard');
//     if (!container) return;
//     container.innerHTML = `<div class="loading"><div class="spinner"></div><p>Loading...</p></div>`;

//     try {
//         const today = new Date().toLocaleDateString('en-CA');
//         let url = '';

//         // if (gutScorecardView === 'daily') {
//         //     url = `/gut/scorecard/daily?patient_id=${gutPatientId}&date=${today}`;
//         // if (gutScorecardView === 'daily') {
//         //     const now  = new Date();
//         //     now.setDate(now.getDate() + gutDailyOffset);
//         //     const date = now.toLocaleDateString('en-CA');
//         //     url = `/gut/scorecard/daily?patient_id=${gutPatientId}&date=${date}`;
//         // ── Daily: render + nav + empty state ─────────────────────────────
//         if (gutScorecardView === 'daily') {

//             // Helper to get nav label
//             const navNow = new Date();
//             navNow.setDate(navNow.getDate() + gutDailyOffset);
//             const dateLabel = gutDailyOffset ===  0 ? 'Today'
//                             : gutDailyOffset === -1 ? 'Yesterday'
//                             : navNow.toLocaleDateString('en-AU', {
//                                 weekday:'short',
//                                 day:'numeric',
//                                 month:'short'
//                               });

//             // Empty state — no meals this day
//             if (!data.meal_count || data.meal_count === 0) {
//                 container.innerHTML = `
//                     <div style="text-align:center;padding:32px 16px">
//                         <div style="font-size:2rem;margin-bottom:8px">
//                             🍽️
//                         </div>
//                         <p class="hint">
//                             No meals logged ${
//                                 gutDailyOffset === 0
//                                     ? 'today' : 'on this day'
//                             } yet.
//                         </p>
//                         ${gutDailyOffset === 0
//                             ? `<p class="hint" style="margin-top:6px">
//                                    Log your first meal above!
//                                </p>`
//                             : ''}
//                     </div>`;
//             } else {
//                 // Has data — render scorecard
//                 renderDailyScorecard(container, data);
//             }

//             // Always add nav for daily (even on empty days)
//             const nav = document.createElement('div');
//             nav.className = 'scorecard-week-nav';
//             nav.innerHTML = `
//                 <button onclick="shiftDay(-1)">← Prev</button>
//                 <span>${dateLabel}</span>
//                 <button onclick="shiftDay(1)"
//                         ${gutDailyOffset >= 0
//                             ? 'disabled style="opacity:.4"'
//                             : ''}>
//                     Next →
//                 </button>`;
//             container.insertBefore(nav, container.firstChild);
//             return;
        

//         } else if (gutScorecardView === 'weekly') {
//             const now  = new Date();
//             const from = new Date(now);
//             from.setDate(now.getDate() - 6 + (gutWeekOffset * 7));
//             url = `/gut/scorecard/weekly?patient_id=${gutPatientId}&week_start=${from.toLocaleDateString('en-CA')}&days=7`;

//         } else {
//             const now      = new Date();
//             const rawMonth = now.getMonth() + 1 + gutMonthOffset;
//             const adjYear  = now.getFullYear() + Math.floor((rawMonth - 1) / 12);
//             const adjMonth = ((rawMonth - 1 + 120) % 12) + 1;
//             url = `/gut/scorecard/monthly?patient_id=${gutPatientId}&year=${adjYear}&month=${adjMonth}`;
//         }

//         const res  = await fetch(url);
//         const data = await res.json();

//         if (data.error) {
//             container.innerHTML = `<p class="hint">Error: ${data.error}</p>`;
//             return;
//         }

//         // Daily — fallback to last date with data if today empty
//         if (gutScorecardView === 'daily' &&
//             (!data.meal_count || data.meal_count === 0)) {
//             const fallback = await fetchLastMealDate();
//             if (fallback && fallback !== today) {
//                 const res2  = await fetch(
//                     `/gut/scorecard/daily?patient_id=${gutPatientId}&date=${fallback}`
//                 );
//                 const data2 = await res2.json();
//                 if (data2.meal_count > 0) {
//                     renderDailyScorecard(container, data2);
//                     const banner = document.createElement('div');
//                     banner.className = 'scorecard-date-banner';
//                     banner.innerHTML = `
//                         <span>📅 Showing ${fallback}</span>
//                         <span class="scorecard-date-hint">
//                             No meals logged today yet
//                         </span>`;
//                     container.insertBefore(banner, container.firstChild);
//                     return;
//                 }
//             }
//             container.innerHTML = `
//                 <div style="text-align:center;padding:32px 16px">
//                     <div style="font-size:2.5rem;margin-bottom:12px">🍽️</div>
//                     <p class="hint">No meals logged yet.</p>
//                     <p class="hint" style="margin-top:8px">
//                         Log your first meal to see your gut scorecard!
//                     </p>
//                 </div>`;
//             return;
//         }

//         // ── Render FIRST, then insert nav on top ──────────────────────────
//         if (gutScorecardView === 'daily')   renderDailyScorecard(container, data);
//         if (gutScorecardView === 'weekly')  renderWeeklyScorecard(container, data);
//         if (gutScorecardView === 'monthly') renderMonthlyScorecard(container, data);

//         // ── Add navigation AFTER render (so it doesn't get wiped) ─────────
//         if (gutScorecardView === 'weekly') {
//             const now  = new Date();
//             const from = new Date(now);
//             const to   = new Date(now);
//             from.setDate(now.getDate() - 6 + (gutWeekOffset * 7));
//             to.setDate(now.getDate() + (gutWeekOffset * 7));

//             const weekLabel = gutWeekOffset === 0
//                 ? 'Last 7 Days'
//                 : `${from.toLocaleDateString('en-AU', {day:'numeric', month:'short'})}–${to.toLocaleDateString('en-AU', {day:'numeric', month:'short'})}`;

//             const nav = document.createElement('div');
//             nav.className = 'scorecard-week-nav';
//             nav.innerHTML = `
//                 <button onclick="shiftWeek(-1)">← Prev</button>
//                 <span>${weekLabel}</span>
//                 <button onclick="shiftWeek(1)"
//                         ${gutWeekOffset >= 0 ? 'disabled style="opacity:.4"' : ''}>
//                     Next →
//                 </button>`;
//             container.insertBefore(nav, container.firstChild);
//         }

//         if (gutScorecardView === 'monthly') {
//             const now      = new Date();
//             const rawMonth = now.getMonth() + 1 + gutMonthOffset;
//             const adjYear  = now.getFullYear() + Math.floor((rawMonth - 1) / 12);
//             const adjMonth = ((rawMonth - 1 + 120) % 12) + 1;
//             const mNames   = ['Jan','Feb','Mar','Apr','May','Jun',
//                               'Jul','Aug','Sep','Oct','Nov','Dec'];

//             const nav = document.createElement('div');
//             nav.className = 'scorecard-week-nav';
//             nav.innerHTML = `
//                 <button onclick="shiftMonth(-1)">← Prev</button>
//                 <span>${mNames[adjMonth-1]} ${adjYear}</span>
//                 <button onclick="shiftMonth(1)"
//                         ${gutMonthOffset >= 0 ? 'disabled style="opacity:.4"' : ''}>
//                     Next →
//                 </button>`;
//             container.insertBefore(nav, container.firstChild);
//         }

//     } catch (err) {
//         container.innerHTML =
//             `<p class="hint">Could not load: ${err.message}</p>`;
//     }
// }

// async function fetchLastMealDate() {
//     try {
//         const res  = await fetch(`/gut/history?patient_id=${gutPatientId}`);
//         const data = await res.json();
//         if (!data.length) return null;
//         const last = data[data.length - 1];
//         return (last.timestamp || last.date || '').slice(0, 10);
//     } catch {
//         return null;
//     }
// }
// ── TAB 2: MY FOOD PLAN ───────────────────────────────────────────────────────
async function loadGutFoodPlan() {
    const container = document.getElementById('gut-plan-content');
    if (!container) return;
    container.innerHTML = `<div class="loading"><div class="spinner"></div><p>Loading plan...</p></div>`;
    try {
        const today = new Date().toLocaleDateString('en-CA');
        const res   = await fetch(`/gut/food-plan?patient_id=${gutPatientId}&date=${today}`);
        const data  = await res.json();
        if (data.error) { container.innerHTML = `<p class="hint">Error: ${data.error}</p>`; return; }
        if (!data.has_profile) {
            container.innerHTML = `
                <div class="card">
                    <div style="text-align:center;padding:32px 16px">
                        <div style="font-size:2.5rem;margin-bottom:12px">⚙️</div>
                        <h3 style="color:white;margin-bottom:8px">Set Up Your Profile First</h3>
                        <p class="hint">Add your bacteria targets and food goals in the Profile tab.</p>
                        <button class="btn-primary" style="margin-top:16px"
                                onclick="showGutTab('profile',document.querySelectorAll('.gut-tab')[3])">
                            Go to Profile ⚙️
                        </button>
                    </div>
                </div>`;
            return;
        }
        renderFoodPlan(container, data);
    } catch (err) {
        container.innerHTML = `<p class="hint">Could not load plan: ${err.message}</p>`;
    }
}

// ── TAB 3: HISTORY ────────────────────────────────────────────────────────────
// async function loadGutHistory() {
//     const container = document.getElementById('gut-history-list');
//     if (!container) return;
//     try {
//         const res  = await fetch(`/gut/history?patient_id=${gutPatientId}`);
//         const data = await res.json();
//         if (!data.length) {
//             container.innerHTML = '<p class="hint">No gut meals logged yet.</p>'; return;
//         }
//         container.innerHTML = [...data].reverse().map(meal => {
//             const s     = meal.overall_gut_score || 0;
//             const color = s >= 7 ? '#22c55e' : s >= 5 ? '#f59e0b' : '#ef4444';
//             const foods = (meal.foods || []).map(f => f.name).join(' · ');
//             return `
//                 <div class="history-item">
//                     <div class="history-date">📅 ${meal.timestamp || ''}</div>
//                     <div class="history-desc">${meal.meal_description || ''}</div>
//                     <div class="history-foods">${foods}</div>
//                     <div class="history-meta">
//                         <span style="color:${color};font-weight:600">🦠 Gut Score: ${s}/10</span>
//                     </div>
//                 </div>`;
//         }).join('');
//     } catch (err) {
//         container.innerHTML = '<p class="hint">Could not load history.</p>';
//     }
// }

// ── TAB 3: HISTORY ────────────────────────────────────────────────────────────
// ── TAB 3: HISTORY — Time Ribbon ─────────────────────────────────────────────
async function loadGutHistory() {
    const container = document.getElementById('gut-history-list');
    if (!container) return;
    try {
        const res  = await fetch(`/gut/history?patient_id=${gutPatientId}`);
        const data = await res.json();

        if (!data.length) {
            container.innerHTML = `
                <div style="text-align:center;padding:32px 16px">
                    <div style="font-size:2.5rem;margin-bottom:12px">🍽️</div>
                    <p class="hint">No gut meals logged yet.</p>
                    <p class="hint" style="margin-top:6px">
                        Log your first meal to start your journal!
                    </p>
                </div>`;
            return;
        }

        // Group by date, newest first
        const byDate = {};
        [...data].reverse().forEach(meal => {
            const date = (meal.timestamp || meal.date || '').slice(0, 10);
            if (!byDate[date]) byDate[date] = [];
            byDate[date].push(meal);
        });

        container.innerHTML = Object.entries(byDate)
            .map(([date, meals]) => renderDayRibbon(date, meals))
            .join('');

    } catch (err) {
        container.innerHTML = '<p class="hint">Could not load history.</p>';
    }
}

// ── Meal slot classifier ───────────────────────────────────────────────────────
function getMealSlot(timestamp) {
    const timeStr = (timestamp || '').slice(11, 16); // "HH:MM"
    if (!timeStr) return { label: 'Meal', emoji: '🍽️', color: '#6b7280', order: 99 };

    const [h, m] = timeStr.split(':').map(Number);
    const mins   = h * 60 + m;

    if (mins >= 360  && mins < 600)  // 6am–10am
        return { label: 'Breakfast', emoji: '🌅', color: '#f59e0b', order: 1 };
    if (mins >= 600  && mins < 720)  // 10am–12pm
        return { label: 'Mid-morning', emoji: '🌤️', color: '#fb923c', order: 2 };
    if (mins >= 720  && mins < 900)  // 12pm–3pm
        return { label: 'Lunch', emoji: '☀️', color: '#22c55e', order: 3 };
    if (mins >= 900  && mins < 1080) // 3pm–6pm
        return { label: 'Snack', emoji: '🍵', color: '#8b5cf6', order: 4 };
    if (mins >= 1080 && mins < 1260) // 6pm–9pm
        return { label: 'Dinner', emoji: '🌆', color: '#3b82f6', order: 5 };
    if (mins >= 1260)                // 9pm+
        return { label: 'Late night', emoji: '🌙', color: '#6366f1', order: 6 };

    return { label: 'Morning', emoji: '🌅', color: '#f59e0b', order: 1 };
}

// ── Render one day ─────────────────────────────────────────────────────────────
function renderDayRibbon(date, meals) {
    const dateLabel = new Date(date + 'T12:00:00')
        .toLocaleDateString('en-AU', {
            weekday: 'long', day: 'numeric', month: 'long'
        });

    // Day average score
    const scores   = meals.map(m => m.overall_gut_score || 0).filter(s => s > 0);
    const avgScore = scores.length
        ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length * 10) / 10
        : 0;
    const dayColor = avgScore >= 7 ? '#22c55e'
                   : avgScore >= 5 ? '#f59e0b' : '#ef4444';

    // Group meals by slot — multiple meals in same slot stack together
    const slotMap = {};
    meals.forEach((meal, idx) => {
        const slot = getMealSlot(meal.timestamp);
        const key  = slot.order;
        if (!slotMap[key]) slotMap[key] = { slot, meals: [] };
        slotMap[key].meals.push({ meal, idx });
    });

    // Sort by time order
    const slots = Object.values(slotMap)
        .sort((a, b) => a.slot.order - b.slot.order);

    const ribbonItems = slots.map(({ slot, meals: slotMeals }, slotIdx) => {
        const isLast = slotIdx === slots.length - 1;

        const mealItems = slotMeals.map(({ meal, idx }) => {
            const s      = meal.overall_gut_score || 0;
            const sc     = s >= 7 ? '#22c55e' : s >= 5 ? '#f59e0b' : '#ef4444';
            const time   = (meal.timestamp || '').slice(11, 16);
            const foods  = meal.foods || [];
            const fCount = foods.length;
            const mealId = `hist-${date}-${idx}`;

            // Count unique bacteria fed
            const allBact = new Set();
            foods.forEach(f =>
                (f.bacteria_fed || []).forEach(b =>
                    allBact.add(typeof b === 'object' ? b.name : b)
                )
            );

            // Short food names for preview
            const foodPreview = foods
                .slice(0, 3)
                .map(f => f.name)
                .join(', ')
                + (foods.length > 3 ? ` +${foods.length - 3}` : '');

            return `
                <div class="ribbon-meal-card"
                     onclick="toggleHistoryMeal('${mealId}')">
                    <div class="ribbon-meal-row">
                        <!-- Score badge -->
                        <div class="ribbon-score-badge"
                             style="background:${sc}">
                            ${s}
                        </div>
                        <!-- Meal info -->
                        <div class="ribbon-meal-info">
                            <div class="ribbon-meal-foods">
                                ${foodPreview}
                            </div>
                            <div class="ribbon-meal-stats">
                                ${time ? `🕐 ${time}` : ''}
                                · ${fCount} food${fCount !== 1 ? 's' : ''}
                                ${allBact.size
                                    ? ` · 🦠 ${allBact.size}`
                                    : ''}
                            </div>
                        </div>
                        <span class="hist-expand-arrow">›</span>
                    </div>

                    <!-- Full detail panel -->
                    <div class="hist-meal-detail" id="${mealId}">
                        ${renderHistoryMealDetail(meal)}
                    </div>
                </div>`;
        }).join('');

        return `
            <div class="ribbon-slot">
                <!-- Timeline line + dot -->
                <div class="ribbon-line-col">
                    <div class="ribbon-dot"
                         style="background:${slot.color};
                                box-shadow:0 0 0 3px ${slot.color}30">
                    </div>
                    ${!isLast
                        ? `<div class="ribbon-connector"
                                style="background:linear-gradient(to bottom,
                                    ${slot.color}40, transparent)">
                           </div>`
                        : ''}
                </div>

                <!-- Slot content -->
                <div class="ribbon-slot-content">
                    <div class="ribbon-slot-label"
                         style="color:${slot.color}">
                        ${slot.emoji} ${slot.label}
                    </div>
                    ${mealItems}
                </div>
            </div>`;
    }).join('');

    return `
        <div class="hist-date-group">
            <!-- Date header -->
            <div class="hist-date-header">
                <span class="hist-date-label">${dateLabel}</span>
                ${avgScore > 0
                    ? `<span class="hist-day-score"
                              style="color:${dayColor}">
                           Avg ${avgScore}/10
                       </span>`
                    : ''}
            </div>

            <!-- Time ribbon -->
            <div class="ribbon-timeline">
                ${ribbonItems}
            </div>
        </div>`;
}

// ── Toggle meal detail ────────────────────────────────────────────────────────
function toggleHistoryMeal(id) {
    const detail = document.getElementById(id);
    const card   = detail?.closest('.ribbon-meal-card');
    const arrow  = card?.querySelector('.hist-expand-arrow');
    if (!detail) return;
    const isOpen = detail.classList.toggle('open');
    if (arrow) arrow.textContent = isOpen ? '↓' : '›';
    if (isOpen) {
        // Smooth scroll so detail is visible
        setTimeout(() =>
            detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        , 100);
    }
}

// ── Reconstruct original analysis view from saved data ────────────────────────
function renderHistoryMealDetail(meal) {
    const foods = meal.foods || [];
    const score = meal.overall_gut_score || 0;
    const notes = meal.gut_notes || '';
    const sc    = score >= 7 ? '#22c55e' : score >= 5 ? '#f59e0b' : '#ef4444';
    const se    = score >= 7 ? '✅' : score >= 5 ? '⚠️' : '❌';

    const foodCards = foods.map(f => {
        const fc = f.fodmap === 'high'   ? '#ef4444'
                 : f.fodmap === 'medium' ? '#f59e0b' : '#22c55e';

        const bacteriaFedHtml = (f.bacteria_fed || []).map(b => {
            const n = typeof b === 'object' ? b.name            : b;
            const s = typeof b === 'object' ? b.impact_strength : '';
            const m = typeof b === 'object' ? b.mechanism       : '';
            return `
                <div class="bacteria-item bacteria-positive">
                    <span class="bacteria-name">✅ ${n}</span>
                    ${s ? `<span class="bacteria-strength">${s}/10</span>` : ''}
                    ${m ? `<div class="bacteria-mech">${m}</div>` : ''}
                </div>`;
        }).join('');

        const bacteriaHarmedHtml = (f.bacteria_harmed || []).map(b => {
            const n = typeof b === 'object' ? b.name : b;
            return `
                <div class="bacteria-item bacteria-negative">
                    <span class="bacteria-name">❌ ${n}</span>
                </div>`;
        }).join('');

        const fibresHtml = (f.prebiotic_fibres || []).length
            ? `<div class="fibre-tags">
                   ${f.prebiotic_fibres.map(x =>
                       `<span class="fibre-tag">${x}</span>`
                   ).join('')}
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
                    <div class="gut-score-pill" style="color:${fc}">
                        FODMAP:
                        <strong>${(f.fodmap || 'low').toUpperCase()}</strong>
                    </div>
                    ${f.probiotic
                        ? `<div class="gut-score-pill probiotic-badge">
                               🦠 Probiotic
                           </div>` : ''}
                </div>
                ${fibresHtml}
                ${bacteriaFedHtml || bacteriaHarmedHtml ? `
                    <div class="bacteria-section">
                        ${bacteriaFedHtml
                            ? `<div class="bacteria-group">${bacteriaFedHtml}</div>`
                            : ''}
                        ${bacteriaHarmedHtml
                            ? `<div class="bacteria-group">${bacteriaHarmedHtml}</div>`
                            : ''}
                    </div>` : ''}
                ${f.gut_notes
                    ? `<div class="gut-food-notes">💬 ${f.gut_notes}</div>`
                    : ''}
            </div>`;
    }).join('');

    return `
        <div class="gut-overall-score"
             style="border-color:${sc};margin-top:12px">
            <div class="gut-score-circle" style="background:${sc}">
                <span class="gut-score-num">${score}</span>
                <span class="gut-score-label">/ 10</span>
            </div>
            <div class="gut-score-info">
                <div class="gut-score-title">${se} Gut Score</div>
                <div class="gut-score-notes">${notes}</div>
            </div>
        </div>
        <div class="section-label" style="margin-top:12px">
            🥗 Food Breakdown
        </div>
        ${foodCards}`;
}


// ── TAB 4: PROFILE ────────────────────────────────────────────────────────────
async function loadGutProfile() {
    const container = document.getElementById('gut-profile-content');
    if (!container) return;
    try {
        const res  = await fetch(`/gut/profile?patient_id=${gutPatientId}`);
        gutProfile = await res.json();
        renderProfileForm(container, gutProfile);
    } catch (err) {
        container.innerHTML = `<p class="hint">Could not load profile: ${err.message}</p>`;
    }
}

function renderProfileForm(container, profile) {
    const bb = profile.bacteria_boost  || [];
    const br = profile.bacteria_reduce || [];
    const ft = profile.food_targets    || [];
    const fa = profile.foods_add       || [];
    const fr = profile.foods_reduce    || [];
    const m  = profile.metrics         || {};
    const fn = profile.functions       || {};

    const funcLabels = {
        overall_health:'Overall Health', immunity:'Immunity',
        gi_health:'GI Health', mental_wellness:'Mental Wellness',
        weight_management:'Weight Management', sugar_metabolism:'Sugar Metabolism'
    };

    const funcHtml = Object.keys(funcLabels).map(key => {
        const helpful = (fn[key] || {}).helpful || 0;
        const color   = helpful >= 75 ? '#22c55e' : helpful >= 60 ? '#f59e0b' : '#ef4444';
        return `
            <div class="profile-func-row">
                <span class="profile-func-label">${funcLabels[key]}</span>
                <span class="profile-func-val" style="color:${color}">${helpful}%</span>
                <input type="number" min="0" max="100"
                       class="profile-func-input" id="func-${key}"
                       value="${helpful}" placeholder="0–100">
            </div>`;
    }).join('');

    const boostHtml = bb.length ? bb.map((b,i) => `
        <div class="profile-bacteria-row">
            <span class="profile-bact-name">${b.name}</span>
            <span class="profile-bact-level level-low">LOW</span>
            <button class="profile-remove-btn" onclick="removeBoostBacteria(${i})">✕</button>
        </div>`).join('') : '<p class="hint">No bacteria added yet.</p>';

    const reduceHtml = br.length ? br.map((b,i) => `
        <div class="profile-bacteria-row">
            <span class="profile-bact-name">${b.name}</span>
            <span class="profile-bact-level level-high">HIGH</span>
            <button class="profile-remove-btn" onclick="removeReduceBacteria(${i})">✕</button>
        </div>`).join('') : '<p class="hint">No bacteria added yet.</p>';

    const targetsHtml = ft.length ? ft.map((t,i) => `
        <div class="profile-target-row">
            <span class="profile-target-food">${t.food}</span>
            <span class="profile-target-amount">${t.amount_grams}g/${t.frequency}</span>
            ${t.feeds ? `<span class="profile-target-feeds">→ ${t.feeds}</span>` : ''}
            <button class="profile-remove-btn" onclick="removeFoodTarget(${i})">✕</button>
        </div>`).join('') : '<p class="hint">No targets added yet.</p>';

    container.innerHTML = `
        <div class="card">
            <h2>⚙️ My Gut Profile</h2>
            <div class="profile-section">
                <div class="profile-field">
                    <label>Patient Name</label>
                    <input type="text" id="profile-name" value="${profile.name||''}" placeholder="Your name">
                </div>
                <div class="profile-field">
                    <label>Test Provider</label>
                    <input type="text" id="profile-provider" value="${profile.test_provider||''}" placeholder="e.g. MicrobioTx">
                </div>
                <div class="profile-field">
                    <label>Test Date</label>
                    <input type="text" id="profile-test-date" value="${profile.test_date||''}" placeholder="e.g. 04/12/2025">
                </div>
                <div class="profile-field">
                    <label>Doctor</label>
                    <input type="text" id="profile-doctor" value="${profile.doctor||''}" placeholder="Doctor's name">
                </div>
            </div>
        </div>

        <div class="card" style="margin-top:12px">
            <h3 style="color:white;margin-bottom:12px">📊 Overall Metrics</h3>
            <div class="profile-section">
                <div class="profile-field-row">
                    <label>Evenness</label>
                    <input type="number" step="0.1" min="0" max="1" id="metric-evenness" value="${m.evenness||''}" placeholder="0.0–1.0">
                </div>
                <div class="profile-field-row">
                    <label>Diversity</label>
                    <input type="number" step="0.1" min="0" id="metric-diversity" value="${m.diversity||''}" placeholder="e.g. 2.8">
                </div>
                <div class="profile-field-row">
                    <label>F/B Ratio</label>
                    <input type="number" step="0.1" min="0" id="metric-fb" value="${m.fb_ratio||''}" placeholder="e.g. 1.8">
                </div>
            </div>
        </div>

        <div class="card" style="margin-top:12px">
            <h3 style="color:white;margin-bottom:4px">🏥 Function Scores (% helpful bacteria)</h3>
            <p class="hint" style="margin-bottom:12px">From your gut report</p>
            ${funcHtml}
        </div>

        <div class="card" style="margin-top:12px">
            <h3 style="color:#22c55e;margin-bottom:4px">↑ Bacteria to Boost (LOW in your gut)</h3>
            <p class="hint" style="margin-bottom:12px">From "Top microbes to boost" in your report</p>
            <div id="boost-bacteria-list">${boostHtml}</div>
            <div class="profile-add-row">
                <input type="text" id="new-boost-name"
                       placeholder="e.g. Alloprevotella" class="profile-add-input">
                <button class="btn-small btn-green" onclick="addBoostBacteria()">+ Add</button>
            </div>
        </div>

        <div class="card" style="margin-top:12px">
            <h3 style="color:#ef4444;margin-bottom:4px">↓ Bacteria to Reduce (HIGH in your gut)</h3>
            <p class="hint" style="margin-bottom:12px">From "Top microbes to reduce" in your report</p>
            <div id="reduce-bacteria-list">${reduceHtml}</div>
            <div class="profile-add-row">
                <input type="text" id="new-reduce-name"
                       placeholder="e.g. Aeromonas" class="profile-add-input">
                <button class="btn-small btn-red" onclick="addReduceBacteria()">+ Add</button>
            </div>
        </div>

        <div class="card" style="margin-top:12px">
            <h3 style="color:white;margin-bottom:4px">🎯 Doctor's Food Targets</h3>
            <p class="hint" style="margin-bottom:12px">Specific foods + amounts prescribed</p>
            <div id="food-targets-list">${targetsHtml}</div>
            <div class="profile-add-food-row">
                <input type="text" id="new-target-food"
                       placeholder="Food (e.g. raw banana)" class="profile-add-input">
                <input type="number" id="new-target-grams"
                       placeholder="grams" value="100" min="0" style="width:70px">
                <select id="new-target-freq" style="padding:8px;border-radius:6px;background:#1f2937;color:white;border:1px solid #374151">
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="3x/week">3x/week</option>
                </select>
                <button class="btn-small btn-green" onclick="addFoodTarget()">+ Add</button>
            </div>
            <div class="profile-field" style="margin-top:12px">
                <label>Feeds which bacteria? (optional)</label>
                <input type="text" id="new-target-feeds" placeholder="e.g. Akkermansia muciniphila">
            </div>
            <div class="profile-field">
                <label>Alternatives (comma separated)</label>
                <input type="text" id="new-target-alts" placeholder="e.g. green banana, plantain">
            </div>
        </div>

        <div class="card" style="margin-top:12px">
            <h3 style="color:white;margin-bottom:12px">📋 Report Recommendations</h3>
            <div class="profile-field">
                <label>✅ Foods to ADD</label>
                <input type="text" id="profile-foods-add"
                       value="${fa.join(', ')}" placeholder="e.g. Wild Mushrooms, Mangoes">
            </div>
            <div class="profile-field">
                <label>❌ Foods to REDUCE</label>
                <input type="text" id="profile-foods-reduce"
                       value="${fr.join(', ')}" placeholder="e.g. Carrots, Tamarind">
            </div>
        </div>

        <div style="padding:16px">
            <button class="btn-analyze" onclick="saveGutProfile()" style="width:100%">
                💾 Save Profile
            </button>
        </div>`;
}

// function buildSmartReminders(fp, bp) {
//     const hour = new Date().getHours();
//     if (hour < 12) return '';

//     // Build bacteria lookup map
//     const bacteriaFedMap = {};
//     bp.forEach(b => {
//         const genus = b.name.split(' ')[0].toLowerCase();
//         bacteriaFedMap[b.name.toLowerCase()] = b.fed_today;
//         bacteriaFedMap[genus]                = b.fed_today;
//     });

//     function isBacteriaFed(feedsTarget) {
//         if (!feedsTarget) return false;
//         const genus = feedsTarget.split(' ')[0].toLowerCase();
//         return bacteriaFedMap[feedsTarget.toLowerCase()]
//             || bacteriaFedMap[genus]
//             || false;
//     }

//     // Classify food targets
//     const trulyMissed      = fp.filter(f =>
//         f.status === 'missed' && !isBacteriaFed(f.feeds));
//     const missedButFedElse = fp.filter(f =>
//         f.status === 'missed' && f.feeds && isBacteriaFed(f.feeds));
//     const partial          = fp.filter(f => f.status === 'partial');
//     const unfedBacteria    = bp.filter(b => !b.fed_today);

//     // All good!
//     if (!trulyMissed.length && !partial.length && !unfedBacteria.length) {
//         return `
//             <div class="reminder-card reminder-success">
//                 <span class="reminder-icon">🎉</span>
//                 <div>
//                     <div class="reminder-title" style="color:#22c55e">
//                         All targets on track today!
//                     </div>
//                     <div class="reminder-body">
//                         Your gut bacteria are being well fed. Keep it up!
//                     </div>
//                 </div>
//             </div>`;
//     }

//     const isAfternoon = hour >= 12 && hour < 17;
//     const isEvening   = hour >= 17 && hour < 20;
//     const isNight     = hour >= 20;

//     const timeLabel = isAfternoon ? 'Afternoon check-in'
//                     : isEvening   ? 'Still time before dinner!'
//                     : "Today's summary";
//     const timeColor = isAfternoon ? '#f59e0b'
//                     : isEvening   ? '#f97316' : '#6366f1';
//     const timeIcon  = isAfternoon ? '☀️' : isEvening ? '🌆' : '🌙';

//     const reminders = [];

//     // Food missed but bacteria fed elsewhere — info only
//     missedButFedElse.forEach(f => {
//         reminders.push({
//             icon:   '💡',
//             text:   `<strong>${f.food}</strong> not eaten — but that's OK!`,
//             sub:    `${f.feeds ? f.feeds.split(' ')[0] : 'Target bacteria'} was already fed by other foods today.`,
//             alt:    '',
//             color:  '#22c55e',
//             isInfo: true
//         });
//     });

//     // Truly missed — bacteria not fed by anything
//     trulyMissed.forEach(f => {
//         const alt = f.alternatives && f.alternatives.length
//             ? 'Or try: ' + f.alternatives.slice(0,2).join(', ') : '';
//         reminders.push({
//             icon:   '🔴',
//             text:   `<strong>${f.food}</strong> — not eaten today`,
//             sub:    isNight
//                     ? `Add ${f.food} to tomorrow's plan`
//                     : `Add ${f.food} (${f.target_grams}g) to your next meal`,
//             alt:    alt,
//             color:  '#ef4444',
//             isInfo: false
//         });
//     });

//     // Partial — only show before night
//     if (!isNight) {
//         partial.forEach(f => {
//             reminders.push({
//                 icon:   '🟠',
//                 text:   `<strong>${f.food}</strong> — ${f.eaten_grams}g of ${f.target_grams}g`,
//                 sub:    `Have ${f.target_grams - f.eaten_grams}g more before dinner`,
//                 alt:    '',
//                 color:  '#f59e0b',
//                 isInfo: false
//             });
//         });
//     }

//     // Unfed bacteria
//     unfedBacteria.slice(0,3).forEach(b => {
//         const genus = b.name.split(' ')[0];
//         reminders.push({
//             icon:   '🦠',
//             text:   `<strong>${b.name}</strong> not fed today`,
//             sub:    isNight
//                     ? `Feed ${genus} first thing tomorrow`
//                     : `Include a ${genus}-friendly food in your next meal`,
//             alt:    '',
//             color:  '#8b5cf6',
//             isInfo: false
//         });
//     });

//     if (!reminders.length) return '';

//     const metCount = fp.filter(f => f.status === 'met').length;
//     const fedCount = bp.filter(b => b.fed_today).length;

//     const summaryHtml = isNight && fp.length > 0 ? `
//         <div class="reminder-summary">
//             <span>🎯 ${metCount}/${fp.length} food targets met</span>
//             <span>🦠 ${fedCount}/${bp.length} bacteria fed</span>
//         </div>` : '';

//     const items = reminders.map(r => `
//         <div class="reminder-item ${r.isInfo ? 'reminder-item-info' : ''}">
//             <span class="reminder-item-icon">${r.icon}</span>
//             <div class="reminder-item-body">
//                 <div class="reminder-item-text">${r.text}</div>
//                 <div class="reminder-item-sub"
//                      style="${r.isInfo ? 'color:#22c55e' : ''}">
//                     ${r.sub}
//                 </div>
//                 ${r.alt ? `<div class="reminder-item-alt">${r.alt}</div>` : ''}
//             </div>
//         </div>`).join('');

//     return `
//         <div class="reminder-card" style="border-color:${timeColor}">
//             <div class="reminder-header">
//                 <span class="reminder-icon">${timeIcon}</span>
//                 <div>
//                     <div class="reminder-title" style="color:${timeColor}">
//                         ${timeLabel}
//                     </div>
//                     <div class="reminder-subtitle">
//                         ${isNight ? 'Here\'s how today went'
//                                   : 'Here\'s what to focus on'}
//                     </div>
//                 </div>
//             </div>
//             ${summaryHtml}
//             <div class="reminder-items">${items}</div>
//         </div>`;
// }

function buildSmartReminders(fp, bp) {
    const hour = new Date().getHours();
    if (hour < 12) return null; // return null not ''

    const bacteriaFedMap = {};
    bp.forEach(b => {
        bacteriaFedMap[b.name.toLowerCase()] = b.fed_today;
        bacteriaFedMap[b.name.split(' ')[0].toLowerCase()] = b.fed_today;
    });
    function isBacteriaFed(f) {
        if (!f) return false;
        return bacteriaFedMap[f.toLowerCase()]
            || bacteriaFedMap[f.split(' ')[0].toLowerCase()]
            || false;
    }

    const trulyMissed      = fp.filter(f => f.status === 'missed' && !isBacteriaFed(f.feeds));
    const missedButFedElse = fp.filter(f => f.status === 'missed' && f.feeds && isBacteriaFed(f.feeds));
    const partial          = fp.filter(f => f.status === 'partial');
    const unfedBacteria    = bp.filter(b => !b.fed_today);
    const metCount         = fp.filter(f => f.status === 'met').length;
    const fedBactCount     = bp.filter(b => b.fed_today).length;
    const isNight          = hour >= 20;

    return {
        trulyMissed, missedButFedElse, partial,
        unfedBacteria, metCount, fedBactCount,
        isNight,
        hour,
        allGood: !trulyMissed.length && !partial.length && !unfedBacteria.length
    };
}

function renderActionCard(reminder, fp, bp) {
    if (!reminder) return ''; // morning — no card

    const { trulyMissed, missedButFedElse, partial,
            unfedBacteria, metCount, fedBactCount,
            isNight, hour, allGood } = reminder;

    // ── All good! ──────────────────────────────────────────────────────────
    if (allGood) {
        return `
            <div class="action-card action-card-success">
                <div class="action-card-left">
                    <div class="action-score-ring success">
                        <span>🎉</span>
                    </div>
                </div>
                <div class="action-card-right">
                    <div class="action-card-title">All done today!</div>
                    <div class="action-card-sub">
                        ${metCount}/${fp.length} foods ·
                        ${fedBactCount}/${bp.length} bacteria
                    </div>
                    <div class="action-card-msg">
                        Your gut is getting excellent support today.
                        Keep logging!
                    </div>
                </div>
            </div>`;
    }

    // ── Calculate urgency score ────────────────────────────────────────────
    const totalIssues = trulyMissed.length + unfedBacteria.length + partial.length;
    const pctDone     = fp.length > 0
        ? Math.round(((metCount + partial.length * 0.5) / fp.length) * 100)
        : 0;
    const ringColor   = pctDone >= 70 ? '#22c55e'
                      : pctDone >= 40 ? '#f59e0b' : '#ef4444';

    // ── Quick Win — easiest single action ─────────────────────────────────
    let quickWin = null;
    if (partial.length) {
        const p = partial[0];
        const remaining = p.target_grams - p.eaten_grams;
        quickWin = {
            icon: '⚡',
            label: 'Quick Win',
            action: `Top up ${p.food} — just ${remaining}g more`,
            color: '#f59e0b'
        };
    } else if (trulyMissed.length) {
        const m = trulyMissed[0];
        const alt = m.alternatives && m.alternatives.length
            ? ` (or ${m.alternatives[0]})` : '';
        quickWin = {
            icon: '🎯',
            label: 'Priority',
            action: `Add ${m.food}${alt} to your next meal`,
            color: '#ef4444'
        };
    } else if (unfedBacteria.length) {
        const b = unfedBacteria[0];
        quickWin = {
            icon: '🦠',
            label: 'Bacteria',
            action: `Feed ${b.name.split(' ')[0]} — include a prebiotic food now`,
            color: '#8b5cf6'
        };
    }

    // ── Time context ───────────────────────────────────────────────────────
    const isEvening   = hour >= 17 && hour < 20;
    const isAfternoon = hour >= 12 && hour < 17;

    const timeMsg = isNight     ? "Today's wrap-up"
                  : isEvening   ? 'Last chance before dinner!'
                  : 'Afternoon check-in';
    const timeColor = isNight   ? '#6366f1'
                    : isEvening ? '#f97316' : '#f59e0b';
    const timeEmoji = isNight   ? '🌙' : isEvening ? '🌆' : '☀️';

    // ── Compact issue chips ────────────────────────────────────────────────
    const issueChips = [
        ...trulyMissed.map(f => ({
            label: f.food, color: '#ef4444', bg: 'rgba(239,68,68,.12)', icon: '❌'
        })),
        ...partial.map(f => ({
            label: `${f.food} (${f.pct}%)`, color: '#f59e0b',
            bg: 'rgba(245,158,11,.12)', icon: '⚠️'
        })),
        ...unfedBacteria.slice(0,2).map(b => ({
            label: b.name.split(' ')[0], color: '#8b5cf6',
            bg: 'rgba(139,92,246,.12)', icon: '🦠'
        }))
    ];

    const chipsHtml = issueChips.map(c => `
        <span class="action-chip"
              style="color:${c.color};background:${c.bg};border-color:${c.color}">
            ${c.icon} ${c.label}
        </span>`).join('');

    // ── Friendly info items (food already covered) ─────────────────────────
    const infoHtml = missedButFedElse.length ? `
        <div class="action-info-row">
            💡 ${missedButFedElse.map(f =>
                `<strong>${f.food}</strong> skipped but
                 ${f.feeds ? f.feeds.split(' ')[0] : 'bacteria'}
                 fed by other foods ✅`
            ).join(' · ')}
        </div>` : '';

    return `
        <div class="action-card" style="border-color:${timeColor}">

            <!-- Header row -->
            <div class="action-card-header">
                <div class="action-card-left">
                    <div class="action-score-ring"
                         style="--ring-color:${ringColor}">
                        <span class="action-ring-pct"
                              style="color:${ringColor}">
                            ${pctDone}%
                        </span>
                    </div>
                </div>
                <div class="action-card-right">
                    <div class="action-card-title"
                         style="color:${timeColor}">
                        ${timeEmoji} ${timeMsg}
                    </div>
                    <div class="action-card-sub">
                        ${metCount}/${fp.length} foods ·
                        ${fedBactCount}/${bp.length} bacteria fed
                    </div>
                </div>
            </div>

            <!-- Quick win CTA -->
            ${quickWin ? `
                <div class="action-quickwin"
                     style="border-color:${quickWin.color};
                            background:${quickWin.color}18">
                    <span class="action-quickwin-icon">
                        ${quickWin.icon}
                    </span>
                    <div>
                        <div class="action-quickwin-label"
                             style="color:${quickWin.color}">
                            ${quickWin.label}
                        </div>
                        <div class="action-quickwin-action">
                            ${quickWin.action}
                        </div>
                    </div>
                </div>` : ''}

            <!-- Issue chips -->
            ${issueChips.length ? `
                <div class="action-chips-row">${chipsHtml}</div>` : ''}

            <!-- Info (bacteria covered by other foods) -->
            ${infoHtml}

            <!-- Night summary -->
            ${isNight ? `
                <div class="action-night-note">
                    Plan these for tomorrow:
                    ${trulyMissed.slice(0,3).map(f =>
                        `<strong>${f.food}</strong>`).join(', ')}
                </div>` : ''}
        </div>`;
}

function renderFoodPlan(container, data) {
    const fp = data.food_progress     || [];
    const bp = data.bacteria_progress || [];
    const fa = data.foods_add         || [];
    const fr = data.foods_reduce      || [];

    const reminder    = buildSmartReminders(fp, bp);
    const actionHtml  = renderActionCard(reminder, fp, bp);

    // ── Bacteria pills (compact) ───────────────────────────────────────────
    const fedCount  = bp.filter(b => b.fed_today).length;
    const totalBact = bp.length;

    const bacteriaPillsHtml = bp.map((b, idx) => {
        const color = b.fed_today ? '#22c55e' : '#ef4444';
        const bg    = b.fed_today
                      ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)';
        const genus = b.name.split(' ')[0];
        return `
            <div class="bact-pill"
                 style="border-color:${color};background:${bg}"
                 onclick="toggleBactDetail('bd-${idx}')">
                <span class="bact-pill-icon">
                    ${b.fed_today ? '✅' : '❌'}
                </span>
                <span class="bact-pill-name">${genus}</span>
                ${b.fed_today
                    ? `<span class="bact-pill-count" style="color:${color}">
                           ${b.fed_count}x
                       </span>`
                    : ''}
            </div>
            <div class="bact-detail" id="bd-${idx}">
                <strong>${b.name}</strong>
                ${b.fed_today
                    ? `<div>Via: ${b.fed_by.join(', ')}</div>`
                    : `<div style="color:#ef4444">Not fed today — log a meal with ${genus} foods</div>`}
                ${b.functions && b.functions.length
                    ? `<div>Supports: ${b.functions.join(', ')}</div>` : ''}
            </div>`;
    }).join('');

    // Detailed bars (hidden by default)
    const bacteriaDetailHtml = bp.map(b => {
        const pct   = Math.min(100, Math.round((b.fed_count / 3) * 100));
        const color = b.fed_today ? '#22c55e' : '#ef4444';
        return `
            <div class="bacteria-boost-row">
                <div class="bacteria-boost-header">
                    <span class="bacteria-boost-name">
                        ${b.fed_today ? '✅' : '❌'} ${b.name}
                    </span>
                    <span class="bacteria-boost-status" style="color:${color}">
                        ${b.fed_today ? `Fed ${b.fed_count}x` : 'Not fed'}
                    </span>
                </div>
                <div class="bacteria-boost-bar-row">
                    <div class="gut-bar-bg" style="flex:1">
                        <div class="gut-bar-fill"
                             style="width:${pct}%;background:${color}">
                        </div>
                    </div>
                    <span class="bacteria-boost-pct" style="color:${color}">
                        ${pct}%
                    </span>
                </div>
                ${b.fed_by && b.fed_by.length
                    ? `<div class="plan-food-meta">Via: ${b.fed_by.join(', ')}</div>` : ''}
            </div>`;
    }).join('');

    // ── Food targets — compact pills summary + collapsible table ──────────
    const metCount = fp.filter(f => f.status === 'met').length;
    const partCount = fp.filter(f => f.status === 'partial').length;

    const foodPillsHtml = fp.map((f, idx) => {
        const color = f.status === 'met'     ? '#22c55e'
                    : f.status === 'partial' ? '#f59e0b' : '#ef4444';
        const bg    = f.status === 'met'     ? 'rgba(34,197,94,.12)'
                    : f.status === 'partial' ? 'rgba(245,158,11,.12)'
                    :                          'rgba(239,68,68,.12)';
        const icon  = f.status === 'met' ? '✅'
                    : f.status === 'partial' ? '⚠️' : '❌';
        // Short food name (first word)
        const shortName = f.food.split(' ')[0];
        return `
            <div class="bact-pill"
                 style="border-color:${color};background:${bg}"
                 onclick="toggleBactDetail('fd-${idx}')">
                <span class="bact-pill-icon">${icon}</span>
                <span class="bact-pill-name">${shortName}</span>
                ${f.status !== 'missed'
                    ? `<span class="bact-pill-count" style="color:${color}">
                           ${f.pct}%
                       </span>`
                    : ''}
            </div>
            <div class="bact-detail" id="fd-${idx}">
                <strong>${f.food}</strong>
                <div>${f.eaten_grams}g eaten of ${f.target_grams}g target</div>
                ${f.feeds ? `<div>Feeds: ${f.feeds}</div>` : ''}
                ${f.alternatives && f.alternatives.length
                    ? `<div>Alternatives: ${f.alternatives.join(', ')}</div>` : ''}
            </div>`;
    }).join('');

    const foodTableRows = fp.map(f => {
        const color = f.status === 'met'     ? '#22c55e'
                    : f.status === 'partial' ? '#f59e0b' : '#ef4444';
        const icon  = f.status === 'met' ? '✅'
                    : f.status === 'partial' ? '⚠️' : '❌';
        const pct   = Math.min(100, f.pct);
        return `
            <tr>
                <td class="plan-table-food">
                    ${icon} ${f.food}
                    ${f.feeds
                        ? `<div class="plan-table-feeds">
                               → ${f.feeds.split(' ')[0]}
                           </div>` : ''}
                </td>
                <td class="plan-table-target">${f.target_grams}g</td>
                <td class="plan-table-eaten" style="color:${color}">
                    ${f.eaten_grams}g
                </td>
                <td class="plan-table-bar">
                    <div class="gut-bar-bg" style="height:6px">
                        <div class="gut-bar-fill"
                             style="width:${pct}%;
                                    background:${color};height:6px">
                        </div>
                    </div>
                </td>
            </tr>`;
    }).join('');

    // ── Report recommendations (collapsed) ────────────────────────────────
    const reportHtml = (fa.length || fr.length) ? `
        <div class="plan-collapse-card" style="margin-top:10px">
            <div class="plan-collapse-header"
                 onclick="togglePlanSection('report-section','report-arrow')">
                <span>📋 Report Recommendations</span>
                <span class="plan-collapse-arrow" id="report-arrow">›</span>
            </div>
            <div id="report-section" style="display:none;margin-top:12px">
                ${fa.length ? `
                    <div class="plan-section-label">✅ Add:</div>
                    <div class="plan-tags">
                        ${fa.map(f =>
                            `<span class="plan-tag plan-tag-add">${f}</span>`
                        ).join('')}
                    </div>` : ''}
                ${fr.length ? `
                    <div class="plan-section-label" style="margin-top:8px">
                        ❌ Reduce:
                    </div>
                    <div class="plan-tags">
                        ${fr.map(f =>
                            `<span class="plan-tag plan-tag-reduce">${f}</span>`
                        ).join('')}
                    </div>` : ''}
            </div>
        </div>` : '';

    // ── Final layout ───────────────────────────────────────────────────────
    container.innerHTML = `

        <!-- Action card (time-aware, most important) -->
        ${actionHtml}

        <!-- Bacteria Boost — compact pills + collapsible detail -->
        <div class="card" style="margin-top:10px">
            <div class="plan-section-header">
                <h3 style="color:white;margin:0;font-size:.95rem">
                    🦠 Bacteria Boost
                </h3>
                <span class="plan-fed-badge">
                    ${fedCount}/${totalBact} fed
                </span>
            </div>
            <div class="bact-summary-row">${bacteriaPillsHtml}</div>
            <div class="plan-collapse-header" style="margin-top:10px"
                 onclick="togglePlanSection('bact-detail','bact-arrow')">
                <span style="font-size:.78rem;color:#9ca3af">
                    See full detail
                </span>
                <span class="plan-collapse-arrow" id="bact-arrow">›</span>
            </div>
            <div id="bact-detail" style="display:none;margin-top:8px">
                ${bacteriaDetailHtml}
            </div>
        </div>

        <!-- Food Targets — compact pills + collapsible table -->
        <div class="card" style="margin-top:10px">
            <div class="plan-section-header">
                <h3 style="color:white;margin:0;font-size:.95rem">
                    🎯 Food Targets
                </h3>
                <span class="plan-fed-badge">
                    ${metCount}/${fp.length} met
                </span>
            </div>
            <div class="bact-summary-row">${foodPillsHtml}</div>
            <div class="plan-collapse-header" style="margin-top:10px"
                 onclick="togglePlanSection('food-detail','food-arrow')">
                <span style="font-size:.78rem;color:#9ca3af">
                    See full table
                </span>
                <span class="plan-collapse-arrow" id="food-arrow">›</span>
            </div>
            <div id="food-detail" style="display:none;margin-top:8px">
                <div class="table-container">
                    <table class="nutrition-table plan-table">
                        <thead>
                            <tr>
                                <th>Food</th>
                                <th>Target</th>
                                <th>Eaten</th>
                                <th>Progress</th>
                            </tr>
                        </thead>
                        <tbody>${foodTableRows}</tbody>
                    </table>
                </div>
            </div>
        </div>

        ${reportHtml}

        <div style="text-align:center;padding:16px">
            <button class="btn-primary"
                    onclick="window.scrollTo({top:0,behavior:'smooth'})">
                📷 Log a Meal
            </button>
        </div>`;
}

function toggleBactDetail(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function togglePlanSection(sectionId, arrowId) {
    const section = document.getElementById(sectionId);
    const arrow   = document.getElementById(arrowId);
    if (!section) return;
    const isOpen = section.style.display !== 'none';
    section.style.display = isOpen ? 'none' : 'block';
    if (arrow) arrow.textContent = isOpen ? '›' : '↓';
}

// ── Profile helpers ────────────────────────────────────────────────────────────
function addBoostBacteria() {
    const name = document.getElementById('new-boost-name').value.trim();
    if (!name) return;
    gutProfile = gutProfile || {};
    gutProfile.bacteria_boost = gutProfile.bacteria_boost || [];
    gutProfile.bacteria_boost.push({ name, level: 'low', functions: [] });
    document.getElementById('new-boost-name').value = '';
    refreshBacteriaList('boost');
}
function removeBoostBacteria(i) {
    if (!gutProfile) return;
    gutProfile.bacteria_boost.splice(i, 1);
    refreshBacteriaList('boost');
}
function addReduceBacteria() {
    const name = document.getElementById('new-reduce-name').value.trim();
    if (!name) return;
    gutProfile = gutProfile || {};
    gutProfile.bacteria_reduce = gutProfile.bacteria_reduce || [];
    gutProfile.bacteria_reduce.push({ name, level: 'high', functions: [] });
    document.getElementById('new-reduce-name').value = '';
    refreshBacteriaList('reduce');
}
function removeReduceBacteria(i) {
    if (!gutProfile) return;
    gutProfile.bacteria_reduce.splice(i, 1);
    refreshBacteriaList('reduce');
}
function refreshBacteriaList(type) {
    const list = gutProfile[`bacteria_${type}`] || [];
    const el   = document.getElementById(`${type}-bacteria-list`);
    if (!el) return;
    if (!list.length) { el.innerHTML = '<p class="hint">No bacteria added yet.</p>'; return; }
    const removeFn   = type === 'boost' ? 'removeBoostBacteria' : 'removeReduceBacteria';
    const levelClass = type === 'boost' ? 'level-low' : 'level-high';
    const levelText  = type === 'boost' ? 'LOW' : 'HIGH';
    el.innerHTML = list.map((b,i) => `
        <div class="profile-bacteria-row">
            <span class="profile-bact-name">${b.name}</span>
            <span class="profile-bact-level ${levelClass}">${levelText}</span>
            <button class="profile-remove-btn" onclick="${removeFn}(${i})">✕</button>
        </div>`).join('');
}
function addFoodTarget() {
    const food  = document.getElementById('new-target-food').value.trim();
    const grams = Number(document.getElementById('new-target-grams').value) || 100;
    const freq  = document.getElementById('new-target-freq').value;
    const feeds = document.getElementById('new-target-feeds').value.trim();
    const altsR = document.getElementById('new-target-alts').value.trim();
    const alts  = altsR ? altsR.split(',').map(s => s.trim()) : [];
    if (!food) return;
    gutProfile = gutProfile || {};
    gutProfile.food_targets = gutProfile.food_targets || [];
    gutProfile.food_targets.push({ food, amount_grams: grams, frequency: freq, feeds, alternatives: alts });
    document.getElementById('new-target-food').value  = '';
    document.getElementById('new-target-grams').value = '100';
    document.getElementById('new-target-feeds').value = '';
    document.getElementById('new-target-alts').value  = '';
    refreshFoodTargetList();
}

function removeFoodTarget(i) {
    if (!gutProfile) return;
    gutProfile.food_targets.splice(i, 1);
    refreshFoodTargetList();
}

function refreshFoodTargetList() {
    const list = gutProfile.food_targets || [];
    const el   = document.getElementById('food-targets-list');
    if (!el) return;
    if (!list.length) {
        el.innerHTML = '<p class="hint">No targets added yet.</p>'; return;
    }
    el.innerHTML = list.map((t,i) => `
        <div class="profile-target-row">
            <span class="profile-target-food">${t.food}</span>
            <span class="profile-target-amount">${t.amount_grams}g/${t.frequency}</span>
            ${t.feeds ? `<span class="profile-target-feeds">→ ${t.feeds}</span>` : ''}
            <button class="profile-remove-btn" onclick="removeFoodTarget(${i})">✕</button>
        </div>`).join('');
}

async function saveGutProfile() {
    const get    = id => { const el = document.getElementById(id); return el ? el.value.trim() : ''; };
    const getNum = id => { const el = document.getElementById(id); return el ? Number(el.value)||0 : 0; };

    const funcKeys = ['overall_health','immunity','gi_health',
                      'mental_wellness','weight_management','sugar_metabolism'];
    const functions = {};
    funcKeys.forEach(key => {
        const h = getNum(`func-${key}`);
        functions[key] = { helpful: h, harmful: Math.round(100 - h) };
    });

    const faRaw = get('profile-foods-add');
    const frRaw = get('profile-foods-reduce');

    const updated = {
        ...(gutProfile || {}),
        patient_id:    gutPatientId,
        name:          get('profile-name'),
        test_provider: get('profile-provider'),
        test_date:     get('profile-test-date'),
        doctor:        get('profile-doctor'),
        metrics: {
            evenness:  getNum('metric-evenness'),
            diversity: getNum('metric-diversity'),
            fb_ratio:  getNum('metric-fb')
        },
        functions,
        foods_add:    faRaw ? faRaw.split(',').map(s=>s.trim()).filter(Boolean) : [],
        foods_reduce: frRaw ? frRaw.split(',').map(s=>s.trim()).filter(Boolean) : [],
        bacteria_boost:  gutProfile ? gutProfile.bacteria_boost  || [] : [],
        bacteria_reduce: gutProfile ? gutProfile.bacteria_reduce || [] : [],
        food_targets:    gutProfile ? gutProfile.food_targets    || [] : []
    };

    try {
        const res    = await fetch('/gut/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updated)
        });
        const result = await res.json();
        if (result.error) { showError('Failed to save: ' + result.error); return; }
        gutProfile = result.profile;
        showMessage('✅ Profile saved!');
        setTimeout(() => clearError(), 2000);
    } catch (err) {
        showError('Save failed: ' + err.message);
    }
}

// ── ANALYZE ───────────────────────────────────────────────────────────────────
async function gutAnalyzePhoto() {
    if (!currentImageBase64) { showError('Please take or upload a photo first!'); return; }
    document.getElementById('gut-loading').style.display    = 'block';
    document.getElementById('gut-results').style.display    = 'none';
    document.getElementById('gut-analyze-btn').style.display = 'none';
    try {
        const res  = await fetch('/gut/analyze', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image: currentImageBase64, mime_type: currentMimeType,
                provider: document.getElementById('provider-select')?.value || 'claude',
                timezone: getUserTimezone(), patient_id: gutPatientId,
                image_width: currentImageWidth, image_height: currentImageHeight
            })
        });
        const data = await res.json();
        if (data.error) { showError('Error: ' + data.error); document.getElementById('gut-analyze-btn').style.display = 'block'; return; }
        gutCurrentResults = data; gutMealTimestamp = data.timestamp;
        renderGutResults(data);
    } catch (err) {
        showError('Analysis failed: ' + err.message);
        document.getElementById('gut-analyze-btn').style.display = 'block';
    } finally { document.getElementById('gut-loading').style.display = 'none'; }
}

async function gutAnalyzeVoice(text) {
    if (!text) { showError('Please speak or type your meal first.'); return; }
    const hv = document.getElementById('analyze-voice-btn');
    const gv = document.getElementById('gut-analyze-voice-btn');
    if (hv) hv.style.display = 'none';
    if (gv) gv.style.display = 'none';
    document.getElementById('gut-loading').style.display = 'block';
    document.getElementById('gut-results').style.display = 'none';
    try {
        const res  = await fetch('/gut/analyze-voice', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text, patient_id: gutPatientId,
                provider: document.getElementById('provider-select')?.value || 'claude',
                timezone: getUserTimezone()
            })
        });
        const data = await res.json();
        if (data.error) { showError('Error: ' + data.error); if (gv) gv.style.display = 'block'; return; }
        gutCurrentResults = data; gutMealTimestamp = data.timestamp;
        renderGutResults(data);
    } catch (err) { showError('Analysis failed: ' + err.message); if (gv) gv.style.display = 'block'; }
    finally { document.getElementById('gut-loading').style.display = 'none'; }
}

// ── RENDER RESULTS ─────────────────────────────────────────────────────────────
function renderGutResults(data) {
    const foods = data.foods || [];
    const score = data.overall_gut_score || 0;
    const notes = data.overall_gut_notes || '';
    const sc    = score >= 7 ? '#22c55e' : score >= 5 ? '#f59e0b' : '#ef4444';
    const se    = score >= 7 ? '✅' : score >= 5 ? '⚠️' : '❌';

    const foodRows = foods.map(f => {
        const fc = f.fodmap === 'high' ? '#ef4444' : f.fodmap === 'medium' ? '#f59e0b' : '#22c55e';
        const bf = (f.bacteria_fed || []).map(b => {
            const n = typeof b==='object'?b.name:b;
            const s = typeof b==='object'?b.impact_strength:'';
            const m = typeof b==='object'?b.mechanism:'';
            return `<div class="bacteria-item bacteria-positive"><span class="bacteria-name">✅ ${n}</span>${s?`<span class="bacteria-strength">${s}/10</span>`:''}${m?`<div class="bacteria-mech">${m}</div>`:''}</div>`;
        }).join('');
        const bh = (f.bacteria_harmed || []).map(b => {
            const n = typeof b==='object'?b.name:b;
            return `<div class="bacteria-item bacteria-negative"><span class="bacteria-name">❌ ${n}</span></div>`;
        }).join('');
        const fi = (f.prebiotic_fibres||[]).length ? `<div class="fibre-tags">${f.prebiotic_fibres.map(x=>`<span class="fibre-tag">${x}</span>`).join('')}</div>` : '';
        return `
            <div class="gut-food-card">
                <div class="gut-food-header">
                    <div class="gut-food-name">${f.name}</div>
                    <div class="gut-food-grams">${f.estimated_grams}g</div>
                </div>
                <div class="gut-scores-row">
                    <div class="gut-score-pill">🌱 Prebiotic: <strong>${f.prebiotic_score||0}/10</strong></div>
                    <div class="gut-score-pill">🔥 Anti-inflam: <strong>${f.anti_inflammatory_score||0}/10</strong></div>
                    <div class="gut-score-pill" style="color:${fc}">FODMAP: <strong>${(f.fodmap||'low').toUpperCase()}</strong></div>
                    ${f.probiotic?`<div class="gut-score-pill probiotic-badge">🦠 Probiotic</div>`:''}
                </div>
                ${fi}
                ${bf||bh?`<div class="bacteria-section">${bf?`<div class="bacteria-group">${bf}</div>`:''} ${bh?`<div class="bacteria-group">${bh}</div>`:''}</div>`:''}
                ${f.gut_notes?`<div class="gut-food-notes">💬 ${f.gut_notes}</div>`:''}
            </div>`;
    }).join('');

    const el = document.getElementById('gut-results');
    el.innerHTML = `
        <div class="card">
            <h2>🦠 Gut Impact Results</h2>
            <p class="meal-desc">${data.meal_description||''}</p>
            <div class="gut-overall-score" style="border-color:${sc}">
                <div class="gut-score-circle" style="background:${sc}">
                    <span class="gut-score-num">${score}</span>
                    <span class="gut-score-label">/ 10</span>
                </div>
                <div class="gut-score-info">
                    <div class="gut-score-title">${se} Overall Gut Score</div>
                    <div class="gut-score-notes">${notes}</div>
                </div>
            </div>
            <div class="gut-disclaimer">⚠️ AI-powered estimates — validate with your practitioner</div>
            <div class="section-label">🥗 Food Breakdown</div>
            ${foodRows}
            <div class="confirm-bar">
                <button class="confirm-btn confirm-reject" onclick="gutRejectResults()">
                    <span class="confirm-icon">✕</span><span class="confirm-label">Retake</span>
                </button>
                <button class="confirm-btn confirm-accept" onclick="gutConfirmResults()">
                    <span class="confirm-icon">✓</span><span class="confirm-label">Confirm</span>
                </button>
            </div>
        </div>`;
    el.style.display = 'block';
    el.scrollIntoView({ behavior: 'smooth' });
}

// ── CONFIRM / RETAKE ──────────────────────────────────────────────────────────
async function gutConfirmResults() {
    if (!gutCurrentResults) return;
    try {
        const res    = await fetch('/gut/confirm-meal', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...gutCurrentResults, timezone: getUserTimezone(), patient_id: gutPatientId })
        });
        const result = await res.json();
        if (result.error) { alert('Failed to save: ' + result.error); return; }
        gutCurrentResults = null;
        document.getElementById('gut-results').style.display    = 'none';
        document.getElementById('gut-analyze-btn').style.display = 'none';
        const pp = document.getElementById('photo-preview');
        const ph = document.getElementById('camera-placeholder');
        if (pp) pp.style.display = 'none';
        if (ph) ph.style.display = 'block';
        hideAllAnalyzeButtons();
        voiceText = '';
        const vt = document.getElementById('voice-text');
        if (vt) vt.textContent = '';
        loadGutScorecard();
        if (gutActiveTab === 'plan') loadGutFoodPlan();
        loadGutHistory();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        showMessage('✓ Gut meal saved!');
        setTimeout(() => clearError(), 2000);
    } catch (err) { alert('Save failed: ' + err.message); }
}
function gutRejectResults() {
    gutCurrentResults = null;
    document.getElementById('gut-results').style.display    = 'none';
    document.getElementById('gut-analyze-btn').style.display = 'none';
    const pp = document.getElementById('photo-preview');
    const ph = document.getElementById('camera-placeholder');
    if (pp) pp.style.display = 'none';
    if (ph) ph.style.display = 'block';
    hideAllAnalyzeButtons();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── SCORECARD RENDERERS ───────────────────────────────────────────────────────
function gutScoreColor(s) { return s>=7?'#22c55e':s>=5?'#f59e0b':'#ef4444'; }
function gutScoreEmoji(s) { return s>=7?'✅':s>=5?'⚠️':'❌'; }
function fodmapColor(l)   { return l==='high'?'#ef4444':l==='medium'?'#f59e0b':'#22c55e'; }
function scoreBar(s, max=10) {
    const pct = Math.min(100,(s/max)*100), c = gutScoreColor(s);
    return `<div class="gut-bar-bg"><div class="gut-bar-fill" style="width:${pct}%;background:${c}"></div></div>`;
}
function renderBacteriaFed(bact) {
    const entries = Object.entries(bact);
    if (!entries.length) return '<p class="hint">No bacteria fed recorded.</p>';
    entries.sort((a,b) => b[1].count - a[1].count);
    return entries.map(([name,data],idx) => {
        const c = gutScoreColor(data.avg_strength), p = Math.min(100,(data.avg_strength/10)*100), id = `bf-${idx}`;
        return `<div class="bacteria-row" onclick="toggleExpand('${id}')">
            <div class="bacteria-row-header">
                <span class="bacteria-row-name">✅ ${name}</span>
                <div class="bacteria-row-right">
                    <span class="bacteria-row-count">${data.count}x</span>
                    <span class="bacteria-strength-badge" style="color:${c}">${data.avg_strength}/10</span>
                    <span class="expand-arrow">›</span>
                </div>
            </div>
            <div class="gut-bar-bg"><div class="gut-bar-fill" style="width:${p}%;background:${c}"></div></div>
            <div class="bacteria-expand" id="${id}">

                <div class="bacteria-row-foods">🌿 via: ${(data.from_foods||[]).join(', ')}</div>
                ${data.mechanism?`<div class="bacteria-mech">💬 ${data.mechanism}</div>`:''}
            </div>
        </div>`;
    }).join('');
}
function renderBacteriaHarmed(bact) {
    const entries = Object.entries(bact);
    if (!entries.length) return `<p class="hint" style="color:#22c55e">✅ None harmed</p>`;
    return entries.map(([name,data],idx) => {
        const id = `bh-${idx}`;
        return `<div class="bacteria-row bacteria-row-harm" onclick="toggleExpand('${id}')">
            <div class="bacteria-row-header">
                <span class="bacteria-row-name" style="color:#fca5a5">⚠️ ${name}</span>
                <div class="bacteria-row-right">
                    <span class="bacteria-row-count">${data.count}x</span>
                    <span class="expand-arrow">›</span>
                </div>
            </div>
            <div class="bacteria-expand" id="${id}">
                <div class="bacteria-row-foods">🍽️ via: ${(data.from_foods||[]).join(', ')}</div>
            </div>
        </div>`;
    }).join('');
}
function toggleExpand(id) {
    const el = document.getElementById(id), row = el?.closest('.bacteria-row');
    if (!el) return;
    const o = el.classList.toggle('open');
    const a = row?.querySelector('.expand-arrow');
    if (a) a.textContent = o ? '↓' : '›';
}
function renderPlantDiversity(plants, count, target=30) {
    const pct = Math.min(100,Math.round((count/target)*100));
    const c   = pct>=80?'#22c55e':pct>=50?'#f59e0b':'#ef4444';
    return `<div class="plant-diversity-section">
        <div class="plant-header"><span>🌱 Plant Diversity</span><span style="color:${c};font-weight:600">${count} plants</span></div>
        <div class="gut-bar-bg"><div class="gut-bar-fill" style="width:${pct}%;background:${c}"></div></div>
        <div class="plant-target-label">Target: ${target} different plants per week</div>
        <div class="plant-tags">${plants.map(p=>`<span class="plant-tag">${p}</span>`).join('')}</div>
    </div>`;
}

// function renderDailyScorecard(container, data) {
//     const s = data.daily_gut_score||0, sc = gutScoreColor(s);
//     container.innerHTML = `
//         <div class="gut-overall-score" style="border-color:${sc}">
//             <div class="gut-score-circle" style="background:${sc}">
//                 <span class="gut-score-num">${s}</span>
//                 <span class="gut-score-label">/ 10</span>
//             </div>
//             <div class="gut-score-info">
//                 <div class="gut-score-title">
//                     ${gutScoreEmoji(s)} Daily Gut Score
//                 </div>
//                 <div class="gut-score-notes">
//                     ${data.meal_count} meals · 
//                     ${data.plant_count} plants · 
//                     FODMAP: <span style="color:${fodmapColor(data.fodmap_worst)}">
//                         ${(data.fodmap_worst||'low').toUpperCase()}
//                     </span>
//                 </div>
//             </div>
//         </div>
//         <div class="gut-scores-grid">
//             <div class="gut-score-tile">
//                 <span class="gut-tile-label">🌱 Prebiotic</span>
//                 <span class="gut-tile-value" 
//                       style="color:${gutScoreColor(data.avg_prebiotic)}">
//                     ${data.avg_prebiotic}/10
//                 </span>
//                 ${scoreBar(data.avg_prebiotic)}
//             </div>
//             <div class="gut-score-tile">
//                 <span class="gut-tile-label">🔥 Anti-Inflam</span>
//                 <span class="gut-tile-value"
//                       style="color:${gutScoreColor(data.avg_antiinflam)}">
//                     ${data.avg_antiinflam}/10
//                 </span>
//                 ${scoreBar(data.avg_antiinflam)}
//             </div>
//             <div class="gut-score-tile">
//                 <span class="gut-tile-label">🦠 Probiotic</span>
//                 <span class="gut-tile-value"
//                       style="color:${data.probiotic_meals>0?'#22c55e':'#ef4444'}">
//                     ${data.probiotic_meals>0?'✅ Yes':'❌ None'}
//                 </span>
//             </div>
//             <div class="gut-score-tile">
//                 <span class="gut-tile-label">🌿 FODMAP</span>
//                 <span class="gut-tile-value"
//                       style="color:${fodmapColor(data.fodmap_worst)}">
//                     ${(data.fodmap_worst||'low').toUpperCase()}
//                 </span>
//             </div>
//         </div>
//         <div class="gut-section">
//             <div class="gut-section-title">
//                 🦠 Bacteria Nourished 
//                 <span class="gut-section-hint">tap to expand</span>
//             </div>
//             ${renderBacteriaFed(data.bacteria_fed||{})}
//         </div>
//         <div class="gut-section">
//             <div class="gut-section-title">
//                 ⚠️ Bacteria Harmed
//                 <span class="gut-section-hint">tap to expand</span>
//             </div>
//             ${renderBacteriaHarmed(data.bacteria_harmed||{})}
//         </div>
//         <div class="gut-section">
//             ${renderPlantDiversity(
//                 data.plant_diversity||[], data.plant_count||0, 30)}
//         </div>`;
// }

// ══════════════════════════════════════════════════════════════════════════════
// Daily Gut Summary — tap score circle to expand
// Add these functions to gut_app.js
// ══════════════════════════════════════════════════════════════════════════════

// ── Summary trigger — added to renderDailyScorecard ──────────────────────────
// Replace your existing gut-overall-score div with this version
// that includes the tap-to-expand summary button

function renderDailyScorecard(container, data) {
    gutDailyData = data;
    const s  = data.daily_gut_score || 0;
    const sc = gutScoreColor(s);

    // Only show summary button if 2+ meals logged
    const hasSummary = (data.meal_count || 0) >= 2;

    container.innerHTML = `
        <!-- Score circle — tappable if summary available -->
        <div class="gut-overall-score"
             style="border-color:${sc};
                    ${hasSummary ? 'cursor:pointer' : ''}"
             ${hasSummary
                ? `onclick="toggleDaySummary(this)"`
                // ? `onclick="toggleDaySummary(this, ${JSON.stringify(data).replace(/"/g, '&quot;')})"`
                : ''}>
            <div class="gut-score-circle" style="background:${sc}">
                <span class="gut-score-num">${s}</span>
                <span class="gut-score-label">/ 10</span>
            </div>
            <div class="gut-score-info">
                <div class="gut-score-title">
                    ${gutScoreEmoji(s)} Daily Gut Score
                </div>
                <div class="gut-score-notes">
                    ${data.meal_count} meals ·
                    ${data.plant_count} plants ·
                    FODMAP: <span style="color:${fodmapColor(data.fodmap_worst)}">
                        ${(data.fodmap_worst || 'low').toUpperCase()}
                    </span>
                </div>
                ${hasSummary ? `
                    <div class="summary-tap-hint">
                        📋 Tap for your day summary
                    </div>` : `
                    <div class="summary-tap-hint" style="color:#94a3b8">
                        Log 2+ meals to unlock day summary
                    </div>`}
            </div>
            ${hasSummary ? `
                <span class="summary-expand-arrow">›</span>` : ''}
        </div>

        <!-- Summary panel — hidden by default -->
        <div class="day-summary-panel" id="day-summary-panel"
             style="display:none">
        </div>

        <!-- Rest of scorecard -->
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
                    ${(data.fodmap_worst || 'low').toUpperCase()}
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
                data.plant_count || 0, 30)}
        </div>`;
}

// ── Toggle summary panel ──────────────────────────────────────────────────────
// function toggleDaySummary(scoreEl, data) {
//     const panel = document.getElementById('day-summary-panel');
//     const arrow = scoreEl.querySelector('.summary-expand-arrow');
//     if (!panel) return;

//     const isOpen = panel.style.display !== 'none';
//     if (isOpen) {
//         panel.style.display = 'none';
//         if (arrow) arrow.textContent = '›';
//         return;
//     }

//     // Build summary if not already built
//     if (!panel.innerHTML) {
//         panel.innerHTML = buildDaySummary(data);
//     }

//     panel.style.display = 'block';
//     if (arrow) arrow.textContent = '↓';
//     panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
// }
function toggleDaySummary(scoreEl) {
    const panel = document.getElementById('day-summary-panel');
    const arrow = scoreEl.querySelector('.summary-expand-arrow');
    if (!panel) return;

    const isOpen = panel.style.display !== 'none';
    if (isOpen) {
        panel.style.display = 'none';
        if (arrow) arrow.textContent = '›';
        return;
    }

    // Build summary if not already built
    if (!panel.innerHTML.trim()) {
        const isToday = gutDailyOffset === 0;
        if (!gutDailyData) {
            panel.innerHTML = '<p class="hint" style="padding:12px">No data available.</p>';
        } else {
            panel.innerHTML = buildDaySummary(gutDailyData, isToday);
        }
    }

    panel.style.display = 'block';
    if (arrow) arrow.textContent = '↓';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Build the summary HTML ────────────────────────────────────────────────────
function buildDaySummary(data, isToday = true) {
    const score         = data.daily_gut_score || 0;
    const mealCount     = data.meal_count      || 0;
    const plantCount    = data.plant_count     || 0;
    const bacteriaFed   = data.bacteria_fed    || {};
    const bacteriaHarmed= data.bacteria_harmed || {};
    const name          = (gutProfile && gutProfile.name)
                          ? gutProfile.name.split(' ')[0]
                          : 'there';

    // ── Opening line based on score ───────────────────────────────────────
    const opening = getOpeningLine(score, name, mealCount, bacteriaFed);

    // ── Today's wins ──────────────────────────────────────────────────────
    const wins = buildWins(score, bacteriaFed, plantCount, data.probiotic_meals);

    // ── Tomorrow's priorities ─────────────────────────────────────────────
    const priorities = buildPriorities(bacteriaFed, bacteriaHarmed, data);

    // ── One insight ───────────────────────────────────────────────────────
    const insight = buildInsight(score, bacteriaHarmed, data);

    // ── Motivation close ──────────────────────────────────────────────────
    const close = getClosingLine(score, isToday);

    return `
        <div class="summary-header">
            <span class="summary-title">📋 Your Gut Day</span>
            <span class="summary-date">
                ${(() => {
                    const d = new Date();
                    d.setDate(d.getDate() + gutDailyOffset);
                    return d.toLocaleDateString('en-AU', {
                        weekday: 'long', day: 'numeric', month: 'short'
                    });
                })()}
            </span>
        </div>

        <!-- Opening -->
        <div class="summary-opening">${opening}</div>

        <!-- Wins -->
        ${wins ? `
            <div class="summary-section">
                <div class="summary-section-title">✅ Today's wins</div>
                ${wins}
            </div>` : ''}

        <!-- Priorities -->
        ${priorities ? `
            <div class="summary-section">
                <div class="summary-section-title">
                    🎯 Tomorrow's priorities
                </div>
                ${priorities}
            </div>` : ''}

        <!-- Insight -->
        ${insight ? `
            <div class="summary-section">
                <div class="summary-section-title">💡 One insight</div>
                <div class="summary-insight">${insight}</div>
            </div>` : ''}

        <!-- Close -->
        <div class="summary-close">${close}</div>`;
}

// ── Opening line ──────────────────────────────────────────────────────────────
function getOpeningLine(score, name, mealCount, bacteriaFed) {
    const fedCount = Object.keys(bacteriaFed).length;

    if (score >= 8.5) return `
        <strong>Outstanding gut day, ${name}! 🏆</strong><br>
        A score like ${score} doesn't happen without real effort.
        Your gut bacteria are thriving today.`;

    if (score >= 7.5) return `
        <strong>Strong day for your gut, ${name}! 💪</strong><br>
        ${score}/10 is well above average. Your food choices
        today are making a real difference to your microbiome.`;

    if (score >= 6.5) return `
        <strong>A solid gut day, ${name} 🌱</strong><br>
        ${score}/10 shows you're on the right track.
        A few tweaks tomorrow and you'll be hitting 7+.`;

    if (score >= 5.5) return `
        <strong>A mixed day for your gut, ${name} ⚠️</strong><br>
        ${score}/10 means your gut got some support but
        needed more. ${fedCount > 0
            ? `${fedCount} bacteria were fed which is a good start.`
            : 'Let\'s focus on feeding the right bacteria tomorrow.'}`;

    if (score >= 4) return `
        <strong>Your gut needed more today, ${name} 🔄</strong><br>
        ${score}/10 is below where we want to be.
        Don't worry — one day doesn't define your gut health.
        Tomorrow is a fresh start.`;

    return `
        <strong>Tough day, ${name} — let's reset tomorrow 💙</strong><br>
        A ${score}/10 tells us your gut didn't get the support
        it needed today. That's OK. What matters is what
        you do tomorrow morning.`;
}

// ── Wins section ──────────────────────────────────────────────────────────────
function buildWins(score, bacteriaFed, plantCount, probioticMeals) {
    const wins = [];
    const fedEntries = Object.entries(bacteriaFed);

    // Top fed bacteria
    if (fedEntries.length > 0) {
        const top = fedEntries
            .sort((a, b) => b[1].count - a[1].count)
            .slice(0, 2);
        top.forEach(([name, data]) => {
            const genus = name.split(' ')[0];
            wins.push(getBacteriaWin(genus, name, data.count));
        });
    }

    // Plant diversity
    if (plantCount >= 10) {
        wins.push(`
            <div class="summary-win-item">
                🌱 <strong>${plantCount} different plants</strong> eaten today —
                ${plantCount >= 20
                    ? 'exceptional plant diversity!'
                    : plantCount >= 15
                    ? 'great plant variety!'
                    : 'good plant diversity.'}
            </div>`);
    }

    // Probiotic
    if (probioticMeals > 0) {
        wins.push(`
            <div class="summary-win-item">
                🦠 <strong>Probiotic food</strong> consumed —
                live cultures supporting your gut lining.
            </div>`);
    }

    // Score itself
    if (score >= 7) {
        wins.push(`
            <div class="summary-win-item">
                📊 <strong>${score}/10 gut score</strong> —
                above the healthy threshold of 7.
            </div>`);
    }

    return wins.length
        ? `<div class="summary-wins">${wins.join('')}</div>`
        : '';
}

function getBacteriaWin(genus, fullName, count) {
    const messages = {
        'Faecalibacterium': `
            <div class="summary-win-item">
                ✅ <strong>${genus}</strong> fed ${count}x today —
                your key anti-inflammatory bacteria is active.
            </div>`,
        'Bifidobacterium': `
            <div class="summary-win-item">
                ✅ <strong>${genus}</strong> fed ${count}x today —
                supporting your immune system and gut barrier.
            </div>`,
        'Lactobacillus': `
            <div class="summary-win-item">
                ✅ <strong>${genus}</strong> fed ${count}x today —
                helping maintain a healthy gut pH.
            </div>`,
        'Akkermansia': `
            <div class="summary-win-item">
                ✅ <strong>${genus}</strong> fed ${count}x today —
                your gut lining is getting protection.
            </div>`,
        'Roseburia': `
            <div class="summary-win-item">
                ✅ <strong>${genus}</strong> fed ${count}x today —
                butyrate production supporting colon health.
            </div>`,
    };
    return messages[genus] || `
        <div class="summary-win-item">
            ✅ <strong>${genus}</strong> fed ${count}x today —
            beneficial bacteria getting good support.
        </div>`;
}

// ── Tomorrow's priorities ─────────────────────────────────────────────────────
function buildPriorities(bacteriaFed, bacteriaHarmed, data) {
    const priorities = [];

    // From profile — bacteria not fed today
    if (gutProfile && gutProfile.bacteria_boost) {
        const unfed = gutProfile.bacteria_boost.filter(b => {
            const genus = b.name.split(' ')[0].toLowerCase();
            return !Object.keys(bacteriaFed).some(fed =>
                fed.toLowerCase().includes(genus)
            );
        }).slice(0, 2);

        unfed.forEach(b => {
            const genus = b.name.split(' ')[0];
            const food  = getBacteriaFood(genus);
            priorities.push(`
                <div class="summary-priority-item">
                    <span class="priority-badge priority-red">❌ Missed</span>
                    <div>
                        <strong>${b.name}</strong> not fed today.<br>
                        <span class="priority-action">
                            Tomorrow: ${food}
                        </span>
                    </div>
                </div>`);
        });
    }

    // From food targets — check what was missed
    if (gutProfile && gutProfile.food_targets) {
        const missedFoods = gutProfile.food_targets
            .filter(t => {
                const name = t.food.toLowerCase();
                const plants = (data.plant_diversity || []);
                return !plants.some(p => p.includes(name.split(' ')[0]));
            })
            .slice(0, 2);

        missedFoods.forEach(t => {
            if (priorities.length >= 3) return;
            priorities.push(`
                <div class="summary-priority-item">
                    <span class="priority-badge priority-orange">
                        🎯 Target
                    </span>
                    <div>
                        <strong>${t.food}</strong>
                        (${t.amount_grams}g ${t.frequency})<br>
                        <span class="priority-action">
                            ${t.alternatives && t.alternatives.length
                                ? `Or try: ${t.alternatives[0]}`
                                : 'Add to your first meal tomorrow'}
                        </span>
                    </div>
                </div>`);
        });
    }

    // Harmed bacteria — what to avoid
    const harmedEntries = Object.keys(bacteriaHarmed);
    if (harmedEntries.length > 0 && priorities.length < 3) {
        const genus = harmedEntries[0].split(' ')[0];
        priorities.push(`
            <div class="summary-priority-item">
                <span class="priority-badge priority-purple">💡 Note</span>
                <div>
                    <strong>${harmedEntries[0]}</strong> was harmed today.<br>
                    <span class="priority-action">
                        ${getHarmedAdvice(genus)}
                    </span>
                </div>
            </div>`);
    }

    return priorities.length ? `
        <div class="summary-priorities">
            ${priorities.join('')}
        </div>` : '';
}

// ── Food suggestions for bacteria ─────────────────────────────────────────────
function getBacteriaFood(genus) {
    const foods = {
        'Faecalibacterium': 'oats or cooked & cooled rice at breakfast',
        'Bifidobacterium':  'plain yoghurt or banana',
        'Lactobacillus':    'dahi, kefir or fermented foods',
        'Akkermansia':      'green banana or garlic (cooked)',
        'Roseburia':        'oats, legumes or cooked vegetables',
        'Succinivibrio':    'fresh fruits and vegetables',
        'Selenomonas':      'leafy greens and vegetables',
        'Alloprevotella':   'nuts, seeds or olive oil',
        'Muribaculaceae':   'dietary fibre — oats, vegetables',
        'Sphingomonas':     'plant foods and antioxidants',
    };
    return foods[genus] || 'prebiotic-rich foods like oats or vegetables';
}

// ── Harmed bacteria advice ────────────────────────────────────────────────────
function getHarmedAdvice(genus) {
    const advice = {
        'Roseburia':         'Reduce fried foods — steam or bake instead tomorrow',
        'Faecalibacterium':  'Avoid processed foods and excess sugar tomorrow',
        'Bifidobacterium':   'Cut back on alcohol and processed snacks',
        'Lactobacillus':     'Limit antibiotics and processed foods',
        'Akkermansia':       'Reduce saturated fats and processed meat',
    };
    return advice[genus]
        || 'Balance tomorrow with more plant-based whole foods';
}

// ── One insight ───────────────────────────────────────────────────────────────
function buildInsight(score, bacteriaHarmed, data) {
    const harmedList   = Object.keys(bacteriaHarmed);
    const fodmap       = data.fodmap_worst || 'low';
    const plantCount   = data.plant_count  || 0;
    const probiotics   = data.probiotic_meals || 0;

    // Priority order of insights
    if (harmedList.length > 0) {
        const genus = harmedList[0].split(' ')[0];
        return `<strong>${harmedList[0]}</strong> was harmed today, likely
                from high-fat or processed foods.
                ${getHarmedAdvice(genus)}`;
    }

    if (fodmap === 'high') {
        return `Your highest FODMAP meal today may cause bloating or
                discomfort for IBS. Tomorrow, try cooking onion and
                garlic thoroughly, and swap apples for bananas.`;
    }

    if (plantCount < 5) {
        return `Only ${plantCount} different plants today. Aim for
                10+ daily — each new plant feeds different bacteria.
                Try adding one new vegetable to each meal tomorrow.`;
    }

    if (probiotics === 0) {
        return `No probiotic foods today. Even a small serve of plain
                dahi or yoghurt daily can meaningfully boost your
                Lactobacillus and Bifidobacterium levels over time.`;
    }

    if (score >= 7) {
        return `Consistency is everything in gut health. Repeating
                today's food choices for 4-6 weeks gives your
                beneficial bacteria time to genuinely multiply
                and colonise.`;
    }

    return `Your gut microbiome responds to what you eat within
            24-48 hours. Tomorrow's choices directly affect how
            you feel in 2 days — that's how fast the bacteria respond.`;
}

// ── Closing line ──────────────────────────────────────────────────────────────
// function getClosingLine(score) {
//     if (score >= 8) return `
//         <div class="summary-close-text">
//             🌟 Days like today are what gut recovery looks like.
//             Keep this up consistently and your next test results
//             will reflect it.
//         </div>`;

//     if (score >= 7) return `
//         <div class="summary-close-text">
//             💪 You're building the right habits.
//             Gut health is a marathon — consistency over 4-8 weeks
//             is what moves the needle on your bacteria levels.
//         </div>`;

//     if (score >= 5) return `
//         <div class="summary-close-text">
//             🌱 Every meal is a new opportunity.
//             Your gut bacteria respond within 24 hours —
//             tomorrow morning is your fresh start.
//         </div>`;

//     return `
//         <div class="summary-close-text">
//             💙 One day doesn't define your gut journey.
//             Focus on your first meal tomorrow —
//             start with something prebiotic like oats or banana.
//         </div>`;
// }
function getClosingLine(score, isToday = true) {
    const dayWord = isToday ? 'tomorrow morning' : 'today';
    const tense   = isToday ? 'is' : 'was';

    if (score >= 8) return `
        <div class="summary-close-text">
            🌟 ${isToday
                ? 'Days like today are what gut recovery looks like. Keep this up!'
                : 'This was an outstanding gut day. Results like this build up over time.'}
        </div>`;

    if (score >= 7) return `
        <div class="summary-close-text">
            💪 ${isToday
                ? 'You\'re building the right habits. Consistency over 4-8 weeks moves the needle.'
                : 'A solid day. Stringing days like this together is how gut health improves.'}
        </div>`;

    if (score >= 5) return `
        <div class="summary-close-text">
            🌱 ${isToday
                ? 'Every meal is a new opportunity. Tomorrow morning is your fresh start.'
                : 'Room to improve — but every day is a new data point on your journey.'}
        </div>`;

    return `
        <div class="summary-close-text">
            💙 ${isToday
                ? 'Focus on your first meal tomorrow — start with something prebiotic.'
                : 'One tough day doesn\'t define your gut journey. Keep going.'}
        </div>`;
}

function renderWeeklyScorecard(container, data) {
    const avg = data.avg_gut_score||0, sc = gutScoreColor(avg);
    const today = new Date().toLocaleDateString('en-CA');
    // const dayNames = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    // const dayBars = (data.daily_scorecards||[]).map((day,i) => {
    const dayBars = (data.daily_scorecards||[]).map((day,i) => {
        const dayDate  = new Date(day.date + 'T12:00:00');
        const dayName  = dayDate.toLocaleDateString('en-AU', {weekday:'short'});
        const dayNum   = dayDate.getDate();
        const s = day.daily_gut_score||0, p = Math.min(100,(s/10)*100), c = s>0?gutScoreColor(s):'#374151';
        return `<div class="day-bar-col ${day.date===today?'day-bar-today':''}">
            <div class="day-bar-score" style="color:${c}">${s>0?s:'—'}</div>
            <div class="day-bar-track"><div class="day-bar-fill" style="height:${p}%;background:${c}"></div></div>
            <div class="day-bar-label">${dayName}</div>
            <div class="day-bar-label" style="font-size:.6rem;color:#94a3b8">${dayNum}</div>
            
        </div>`;
    }).join('');
    const bRows = Object.entries(data.bacteria_fed||{}).sort((a,b)=>b[1].count-a[1].count).map(([name,d],i)=>{
        const m = ['🥇','🥈','🥉'][i]||'';
        return `<div class="bacteria-league-row"><span class="league-medal">${m}</span><span class="league-name">${name}</span><span class="league-count">${d.count}x</span><div class="league-bar-bg"><div class="league-bar-fill" style="width:${Math.min(100,(d.count/14)*100)}%;background:${gutScoreColor(d.avg_strength)}"></div></div></div>`;
    }).join('');
    container.innerHTML = `
        <div class="gut-overall-score" style="border-color:${sc}">
            <div class="gut-score-circle" style="background:${sc}"><span class="gut-score-num">${avg}</span><span class="gut-score-label">/ 10</span></div>
            <div class="gut-score-info"><div class="gut-score-title">${gutScoreEmoji(avg)} Weekly Avg</div>
            <div class="gut-score-notes">${data.total_meals||0} meals · ${data.plant_count||0} plants</div>
            ${data.best_day?`<div class="gut-score-notes">🏆 Best: ${data.best_day_score}/10 · 📉 Worst: ${data.worst_day_score}/10</div>`:''}</div>
        </div>
        <div class="gut-section"><div class="gut-section-title">📊 Daily Scores</div><div class="day-bars-row">${dayBars}</div></div>
        <div class="gut-section"><div class="gut-section-title">🦠 Bacteria League</div>${bRows||'<p class="hint">No data yet.</p>'}</div>
        <div class="gut-section">${renderPlantDiversity(data.plant_diversity||[],data.plant_count||0,30)}</div>
        ${Object.keys(data.bacteria_harmed||{}).length?`<div class="gut-section"><div class="gut-section-title">⚠️ Bacteria Harmed</div>${renderBacteriaHarmed(data.bacteria_harmed)}</div>`:''}`;
}
function renderMonthlyScorecard(container, data) {
    const avg = data.avg_gut_score||0, sc = gutScoreColor(avg);
    const mNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const mLabel = `${mNames[(data.month||1)-1]} ${data.year}`;
    const topFoods = (data.top_foods||[]).slice(0,5).map(([n,c],i)=>`<div class="top-food-row"><span class="top-food-rank">${i+1}</span><span class="top-food-name">${n}</span><span class="top-food-count">${c}x</span></div>`).join('');
    const bRows = Object.entries(data.bacteria_fed||{}).sort((a,b)=>b[1].count-a[1].count).slice(0,8).map(([name,d])=>`<div class="bacteria-league-row"><span class="league-name">${name}</span><span class="league-count">${d.count}x</span><div class="league-bar-bg"><div class="league-bar-fill" style="width:${Math.min(100,(d.count/20)*100)}%;background:${gutScoreColor(d.avg_strength)}"></div></div></div>`).join('');
    container.innerHTML = `
        <div class="gut-overall-score" style="border-color:${sc}">
            <div class="gut-score-circle" style="background:${sc}"><span class="gut-score-num">${avg}</span><span class="gut-score-label">/ 10</span></div>
            <div class="gut-score-info"><div class="gut-score-title">${gutScoreEmoji(avg)} ${mLabel}</div>
            <div class="gut-score-notes">${data.total_meals||0} meals · ${data.plant_count||0} plants · ${data.fried_meals||0} fried ${(data.fried_meals||0)>5?'⚠️':'✅'}</div></div>
        </div>
        <div class="gut-section"><div class="gut-section-title">🦠 Bacteria Fed This Month</div>${bRows||'<p class="hint">No data yet.</p>'}</div>
        <div class="gut-section"><div class="gut-section-title">🥗 Most Eaten Foods</div>${topFoods||'<p class="hint">No meals yet.</p>'}</div>
        <div class="gut-section">${renderPlantDiversity(data.plant_diversity||[],data.plant_count||0,120)}</div>
        ${Object.keys(data.bacteria_harmed||{}).length?`<div class="gut-section"><div class="gut-section-title">⚠️ Bacteria Harmed</div>${renderBacteriaHarmed(data.bacteria_harmed)}</div>`:''}`;
}
