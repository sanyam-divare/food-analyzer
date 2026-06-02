# ── Gut Health Engine ───────────────────────────
# Persona 2: Gut Health Mode

import os
import json
import requests
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── Gut-specific prompt ───────────────────────────
GUT_PROMPT = """You are a clinical gut health specialist and nutritionist.
Analyse this food plate image carefully.

For each food item identify:
1. The food name and estimated portion weight
2. Gut health impact including:
   - Prebiotic fibres present (inulin, FOS, beta-glucan, pectin, resistant starch)
   - Whether it contains probiotics (fermented foods only)
   - FODMAP classification (low/medium/high)
   - Anti-inflammatory compounds present
   - Which gut bacteria this food feeds (be specific with species names)
   - Which gut bacteria this food may harm
   - Overall gut health impact score 1-10

IMPORTANT RULES:
- Only list bacteria you are confident this food impacts
- Use full scientific names e.g. "Bifidobacterium longum" not just "Bifidobacterium"
- FODMAP must be one of: low, medium, high
- Prebiotic score 0-10 (0=none, 10=excellent prebiotic)
- Anti-inflammatory score 0-10 (0=inflammatory, 10=strongly anti-inflammatory)

Respond ONLY in this exact JSON format, no other text:
{
    "meal_description": "brief description",
    "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
    "overall_gut_score": 7.2,
    "overall_gut_notes": "brief clinical summary of gut impact",
    "foods": [
        {
            "name": "specific food name",
            "estimated_grams": 150,
            "confidence": "high|medium|low",
            "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|not applicable",
            "category": "protein|grain|vegetable|fruit|dairy|fermented|sauce|condiment",
            "fodmap": "low|medium|high",
            "prebiotic_score": 7.5,
            "probiotic": false,
            "anti_inflammatory_score": 8.0,
            "prebiotic_fibres": ["inulin", "FOS"],
            "bacteria_fed": [
                {
                    "name": "Bifidobacterium longum",
                    "impact_strength": 8,
                    "mechanism": "Rich in inulin which selectively feeds this species"
                }
            ],
            "bacteria_harmed": [],
            "gut_notes": "brief note on gut impact"
        }
    ]
}"""


def analyze_gut_with_claude(image_base64, mime_type="image/jpeg"):
    """Analyze food image with gut-specific prompt using Claude"""
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY"}
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4000,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": GUT_PROMPT
                        }
                    ]
                }]
            },
            timeout=30
        )

        if response.status_code != 200:
            return {"error": f"Claude error {response.status_code}"}

        text = response.json()['content'][0]['text'].strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())

    except Exception as e:
        return {"error": f"Claude gut analysis failed: {e}"}


def analyze_gut_with_gemini(image_base64, mime_type="image/jpeg"):
    """Analyze food image with gut-specific prompt using Gemini"""
    if not GEMINI_API_KEY:
        return {"error": "Missing GEMINI_API_KEY"}
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                    {"text": GUT_PROMPT}
                ]
            }]
        }
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code != 200:
            return {"error": f"Gemini error {response.status_code}"}

        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    except Exception as e:
        return {"error": f"Gemini gut analysis failed: {e}"}


def save_gut_meal_log(meal_data):
    """Save gut meal to separate gut log file"""
    log_file = 'gut_meals_log.json'
    log = []

    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            log = json.load(f)

    # Add date for easy filtering
    timestamp = meal_data.get('timestamp', get_local_timestamp())
    meal_data['date'] = timestamp[:10]

    log.append(meal_data)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)


def calculate_gut_scores(foods):
    """Calculate aggregate gut scores from food list"""
    if not foods:
        return {}

    total_prebiotic    = 0
    total_antiinflam   = 0
    all_bacteria_fed   = []
    all_bacteria_harm  = []
    fodmap_levels      = []

    for food in foods:
        total_prebiotic  += food.get('prebiotic_score', 0) or 0
        total_antiinflam += food.get('anti_inflammatory_score', 0) or 0

        for b in food.get('bacteria_fed', []):
            if isinstance(b, dict):
                all_bacteria_fed.append(b.get('name', ''))
            elif isinstance(b, str):
                all_bacteria_fed.append(b)

        for b in food.get('bacteria_harmed', []):
            if isinstance(b, dict):
                all_bacteria_harm.append(b.get('name', ''))
            elif isinstance(b, str):
                all_bacteria_harm.append(b)

        fodmap = food.get('fodmap', 'low')
        fodmap_levels.append(fodmap)

    count = len(foods)
    # Overall FODMAP = worst level in meal
    fodmap_priority = {'high': 3, 'medium': 2, 'low': 1}
    overall_fodmap = max(fodmap_levels, key=lambda x: fodmap_priority.get(x, 0)) \
                     if fodmap_levels else 'low'

    return {
        "avg_prebiotic_score":         round(total_prebiotic / count, 1),
        "avg_anti_inflammatory_score": round(total_antiinflam / count, 1),
        "bacteria_fed":                list(set(all_bacteria_fed)),
        "bacteria_harmed":             list(set(all_bacteria_harm)),
        "overall_fodmap":              overall_fodmap,
        "probiotic_foods":             [f['name'] for f in foods if f.get('probiotic')]
    }


def get_local_timestamp(timezone_str=None):
    """Get current timestamp in user's local timezone"""
    try:
        if timezone_str and ZoneInfo:
            tz = ZoneInfo(timezone_str)
            return datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── existing functions above ──────────────────────
# analyze_gut_with_claude()
# analyze_gut_with_gemini()
# save_gut_meal_log()
# calculate_gut_scores()
# get_local_timestamp()

# ── NEW: Scorecard functions below ───────────────

def build_daily_gut_scorecard(meals, date):
    """
    Aggregates all gut meals for one day into a scorecard.
    Input:  list of meal dicts from gut_meals_log.json
    Output: complete daily scorecard dict
    """
    if not meals:
        return {
            'date':            date,
            'daily_gut_score': 0,
            'bacteria_fed':    {},
            'bacteria_harmed': {},
            'plant_diversity': [],
            'plant_count':     0,
            'meal_count':      0,
            'avg_prebiotic':   0,
            'avg_antiinflam':  0,
            'fodmap_worst':    'low',
            'probiotic_meals': 0,
            'meals':           []
        }

    bacteria_fed    = {}  # name → {count, total_strength, foods}
    bacteria_harmed = {}  # name → {count, from_foods}
    plants_today    = set()
    gut_scores      = []
    prebiotic_scores  = []
    antiinflam_scores = []
    fodmap_priority = {'high': 3, 'medium': 2, 'low': 1}
    fodmap_worst    = 'low'
    probiotic_meals = 0

    for meal in meals:
        score = meal.get('overall_gut_score', 0)
        if score:
            gut_scores.append(score)

        for food in meal.get('foods', []):
            # ── Plant diversity ───────────────────
            food_name = food.get('name', '').lower().strip()
            if food_name:
                plants_today.add(food_name)

            # ── Scores ────────────────────────────
            pre = food.get('prebiotic_score', 0)
            ani = food.get('anti_inflammatory_score', 0)
            if pre: prebiotic_scores.append(pre)
            if ani: antiinflam_scores.append(ani)

            # ── FODMAP ────────────────────────────
            fodmap = food.get('fodmap', 'low')
            if fodmap_priority.get(fodmap, 0) > fodmap_priority.get(fodmap_worst, 0):
                fodmap_worst = fodmap

            # ── Probiotic ─────────────────────────
            if food.get('probiotic'):
                probiotic_meals += 1

            # ── Bacteria fed ──────────────────────
            for b in food.get('bacteria_fed', []):
                name     = b.get('name', b) if isinstance(b, dict) else b
                strength = b.get('impact_strength', 5) if isinstance(b, dict) else 5
                mech     = b.get('mechanism', '') if isinstance(b, dict) else ''

                if name not in bacteria_fed:
                    bacteria_fed[name] = {
                        'count':          0,
                        'total_strength': 0,
                        'avg_strength':   0,
                        'from_foods':     [],
                        'mechanism':      mech
                    }
                bacteria_fed[name]['count']          += 1
                bacteria_fed[name]['total_strength'] += strength
                bacteria_fed[name]['from_foods'].append(food_name)

            # ── Bacteria harmed ───────────────────
            for b in food.get('bacteria_harmed', []):
                name = b.get('name', b) if isinstance(b, dict) else b

                if name not in bacteria_harmed:
                    bacteria_harmed[name] = {
                        'count':      0,
                        'from_foods': []
                    }
                bacteria_harmed[name]['count']      += 1
                bacteria_harmed[name]['from_foods'].append(food_name)

    # ── Calculate averages ────────────────────────
    for name, data in bacteria_fed.items():
        if data['count'] > 0:
            data['avg_strength'] = round(
                data['total_strength'] / data['count'], 1
            )

    def safe_avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0

    return {
        'date':            date,
        'daily_gut_score': safe_avg(gut_scores),
        'bacteria_fed':    bacteria_fed,
        'bacteria_harmed': bacteria_harmed,
        'plant_diversity': sorted(list(plants_today)),
        'plant_count':     len(plants_today),
        'meal_count':      len(meals),
        'avg_prebiotic':   safe_avg(prebiotic_scores),
        'avg_antiinflam':  safe_avg(antiinflam_scores),
        'fodmap_worst':    fodmap_worst,
        'probiotic_meals': probiotic_meals,
        'meals':           meals   # keep original meals for display
    }


def build_weekly_gut_scorecard(all_meals, week_start_date):
    """
    Aggregates gut meals for 7 days into a weekly scorecard.
    week_start_date: 'YYYY-MM-DD' string for Monday of the week
    """
    from datetime import datetime, timedelta

    # Build list of 7 dates
    start = datetime.strptime(week_start_date, "%Y-%m-%d")
    week_dates = [
        (start + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(7)
    ]

    # Group meals by date
    daily_scorecards = []
    all_plants_week  = set()
    all_bacteria_fed = {}
    gut_scores_by_day = {}

    for date in week_dates:
        day_meals = [
            m for m in all_meals
            if m.get('timestamp', '').startswith(date)
            or m.get('date', '') == date
        ]
        scorecard = build_daily_gut_scorecard(day_meals, date)
        daily_scorecards.append(scorecard)

        # Accumulate weekly data
        if scorecard['daily_gut_score'] > 0:
            gut_scores_by_day[date] = scorecard['daily_gut_score']

        all_plants_week.update(scorecard['plant_diversity'])

        for name, data in scorecard['bacteria_fed'].items():
            if name not in all_bacteria_fed:
                all_bacteria_fed[name] = {
                    'count':      0,
                    'total_strength': 0,
                    'avg_strength':   0
                }
            all_bacteria_fed[name]['count']          += data['count']
            all_bacteria_fed[name]['total_strength'] += data['total_strength']

    # Calculate avg strength per bacteria
    for name, data in all_bacteria_fed.items():
        if data['count'] > 0:
            data['avg_strength'] = round(
                data['total_strength'] / data['count'], 1
            )

    # Sort bacteria by count descending
    sorted_bacteria = dict(
        sorted(all_bacteria_fed.items(),
               key=lambda x: x[1]['count'],
               reverse=True)
    )

    scores = list(gut_scores_by_day.values())
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    best_day  = max(gut_scores_by_day, key=gut_scores_by_day.get) \
                if gut_scores_by_day else None
    worst_day = min(gut_scores_by_day, key=gut_scores_by_day.get) \
                if gut_scores_by_day else None

    return {
        'week_start':        week_start_date,
        'week_end':          week_dates[-1],
        'daily_scorecards':  daily_scorecards,
        'gut_scores_by_day': gut_scores_by_day,
        'avg_gut_score':     avg_score,
        'best_day':          best_day,
        'best_day_score':    gut_scores_by_day.get(best_day, 0),
        'worst_day':         worst_day,
        'worst_day_score':   gut_scores_by_day.get(worst_day, 0),
        'bacteria_fed':      sorted_bacteria,
        'plant_diversity':   sorted(list(all_plants_week)),
        'plant_count':       len(all_plants_week),
        'total_meals':       sum(s['meal_count'] for s in daily_scorecards)
    }


def build_monthly_gut_scorecard(all_meals, year, month):
    """
    Aggregates gut meals for a full month into a monthly report.
    """
    from datetime import datetime
    import calendar

    # Get all dates in the month
    days_in_month = calendar.monthrange(year, month)[1]
    month_str     = f"{year}-{month:02d}"

    month_meals = [
        m for m in all_meals
        if m.get('timestamp', '').startswith(month_str)
        or m.get('date', '').startswith(month_str)
    ]

    all_plants_month = set()
    all_bacteria_fed = {}
    all_bacteria_harmed = {}
    gut_scores       = []
    food_frequency   = {}  # food name → count
    fried_count      = 0

    for meal in month_meals:
        score = meal.get('overall_gut_score', 0)
        if score:
            gut_scores.append(score)

        for food in meal.get('foods', []):
            name = food.get('name', '').lower().strip()
            if name:
                all_plants_month.add(name)
                food_frequency[name] = food_frequency.get(name, 0) + 1

            if food.get('cooking_method', '') == 'fried':
                fried_count += 1

            for b in food.get('bacteria_fed', []):
                bname    = b.get('name', b) if isinstance(b, dict) else b
                strength = b.get('impact_strength', 5) \
                           if isinstance(b, dict) else 5
                if bname not in all_bacteria_fed:
                    all_bacteria_fed[bname] = {
                        'count': 0, 'total_strength': 0
                    }
                all_bacteria_fed[bname]['count']          += 1
                all_bacteria_fed[bname]['total_strength'] += strength

            for b in food.get('bacteria_harmed', []):
                bname = b.get('name', b) if isinstance(b, dict) else b
                all_bacteria_harmed[bname] = \
                    all_bacteria_harmed.get(bname, 0) + 1

    # Top foods
    top_foods = sorted(
        food_frequency.items(), key=lambda x: x[1], reverse=True
    )[:10]

    # Avg strength
    for name, data in all_bacteria_fed.items():
        if data['count'] > 0:
            data['avg_strength'] = round(
                data['total_strength'] / data['count'], 1
            )

    sorted_bacteria = dict(
        sorted(all_bacteria_fed.items(),
               key=lambda x: x[1]['count'],
               reverse=True)
    )

    avg_score = round(sum(gut_scores) / len(gut_scores), 1) \
                if gut_scores else 0

    return {
        'year':              year,
        'month':             month,
        'month_str':         month_str,
        'avg_gut_score':     avg_score,
        'total_meals':       len(month_meals),
        'bacteria_fed':      sorted_bacteria,
        'bacteria_harmed':   all_bacteria_harmed,
        'plant_diversity':   sorted(list(all_plants_month)),
        'plant_count':       len(all_plants_month),
        'top_foods':         top_foods,
        'fried_meals':       fried_count,
        'gut_scores':        gut_scores,
    }