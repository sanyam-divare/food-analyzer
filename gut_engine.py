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

FODMAP RATING — based on ACTUAL PORTION, not food category:
Small amounts of high-FODMAP foods are often LOW/MEDIUM in practice.
Quick reference (rate LOW below these, HIGH above):
  raisins/dried fruit >15g, garlic >1 cooked clove, onion >2 tbsp cooked,
  apple >half, wheat >1 slice, milk >100ml, honey >1 tsp.
Cooking reduces FODMAP — raw garlic/onion rates higher than cooked.
When portion is small/typical for the dish, prefer LOW or MEDIUM over HIGH.

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

def build_gut_prompt(patient_profile=None):
    """Build personalised prompt based on patient profile."""
    if not patient_profile:
        return GUT_PROMPT

    bacteria_boost = [
        b.get('name', b) if isinstance(b, dict) else b
        for b in patient_profile.get('bacteria_boost', [])
    ]
    bacteria_reduce = [
        b.get('name', b) if isinstance(b, dict) else b
        for b in patient_profile.get('bacteria_reduce', [])
    ]
    food_targets = [
        f"{t.get('food','')} {t.get('amount_grams','')}g {t.get('frequency','')}"
        for t in patient_profile.get('food_targets', [])
    ]
    foods_reduce = patient_profile.get('foods_reduce', [])

    # Only personalise if profile has real data
    if not bacteria_boost and not food_targets:
        return GUT_PROMPT

    patient_context = f"""

PATIENT-SPECIFIC CONTEXT — personalise your analysis:

Bacteria to BOOST (patient is deficient — prioritise feeding these):
{chr(10).join(f'  - {b}' for b in bacteria_boost)}

Bacteria to REDUCE (patient has excess — flag if food promotes these):
{chr(10).join(f'  - {b}' for b in bacteria_reduce) if bacteria_reduce else '  None specified'}

Doctor food targets (mention in gut_notes if this meal contains these):
{chr(10).join(f'  - {t}' for t in food_targets) if food_targets else '  None specified'}

Foods to flag (mention clearly in gut_notes if present):
{chr(10).join(f'  - {f}' for f in foods_reduce) if foods_reduce else '  None specified'}

When rating impact_strength for bacteria_fed:
  - Score 8-10 if food directly feeds a BOOST bacteria
  - Score 5-7 if food indirectly supports a BOOST bacteria
  - Score 1-4 for minor or uncertain impact
"""

    # Insert patient context before IMPORTANT RULES
    return GUT_PROMPT.replace(
        'IMPORTANT RULES:',
        patient_context + '\nIMPORTANT RULES:'
    )


DAILY_ANALYSIS_PROMPT = """
You are a clinical gut health analyst reviewing a patient's complete food log.

Patient profile:
- Bacteria to BOOST (currently low): {bacteria_boost}
- Bacteria to REDUCE (currently high): {bacteria_reduce}
- Doctor's food targets: {food_targets}
- Known condition: IBS / gut dysbiosis

Today's complete food log in chronological sequence:
{day_log}

Analyse the ENTIRE day holistically — not each meal in isolation.
Consider:
1. Meal SEQUENCING — did the order of eating help or hurt?
2. Cumulative FODMAP load across the day
3. Bacteria NET EFFECT for each target bacteria
4. Food INTERACTIONS — did any foods cancel each other's benefits?
5. TRUE daily score — more accurate than average of meal scores.

Return ONLY valid JSON, no markdown, no explanation outside JSON:
{{
  "true_daily_score": 6.2,
  "score_adjustment": -0.6,
  "score_reason": "one line why true score differs from average",
  "sequencing_grade": "good|fair|poor",
  "sequencing_insight": "2-3 sentence insight about meal order today",
  "fodmap_status": "within range|borderline|exceeded",
  "fodmap_insight": "1-2 sentences about cumulative FODMAP load",
  "bacteria_net_effect": {{
    "BacteriaName": {{
      "status": "well supported|partially supported|undermined|not fed",
      "reason": "brief reason"
    }}
  }},
  "key_interaction": "Most important food interaction today (1 sentence)",
  "tomorrow_priorities": [
    "Specific action 1",
    "Specific action 2",
    "Specific action 3"
  ],
  "narrative": "2-3 sentence human-friendly summary of the day"
}}
"""

def analyze_gut_with_claude(image_base64, mime_type="image/jpeg", patient_profile=None):
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
                "temperature": 0.1,
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
                            "text": build_gut_prompt(patient_profile)

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


def analyze_gut_with_gemini(image_base64, mime_type="image/jpeg", patient_profile=None):
    """Analyze food image with gut-specific prompt using Gemini"""
    if not GEMINI_API_KEY:
        return {"error": "Missing GEMINI_API_KEY"}
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                    {"text": build_gut_prompt(patient_profile)}
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

def analyze_gut_with_claude_text(voice_text, patient_profile=None):
    """Analyze text/voice description with gut-specific prompt"""
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
                "temperature": 0.1,
                "messages": [{
                    "role": "user",
                    "content": f"Extract food items from this description: '{voice_text}'. "
                               f"Then analyse the gut health impact of each item.\n\n"
                               f"{build_gut_prompt(patient_profile)}"
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
        return {"error": f"Claude gut text analysis failed: {e}"}

        
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
def weighted_meal_score(meals):
    """
    Calculate gut score weighted by meal size (total grams).
    Larger meals have more impact than small snacks.
    """
    weighted_sum  = 0
    total_weight  = 0

    for meal in meals:
        score = meal.get('overall_gut_score', 0)
        if not score:
            continue

        # Total grams in this meal
        meal_grams = sum(
            f.get('estimated_grams', 100)
            for f in meal.get('foods', [])
        )

        # Minimum 50g so even small snacks count
        meal_grams = max(meal_grams, 50)

        weighted_sum += score * meal_grams
        total_weight += meal_grams

    if total_weight == 0:
        return 0

    return round(weighted_sum / total_weight, 1)


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
        'daily_gut_score': weighted_meal_score(meals), #safe_avg(gut_scores),
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



def build_weekly_gut_scorecard(all_meals, week_start):
    """
    Builds scorecard for any 7-day window ending today.
    week_start: YYYY-MM-DD string for first day of window
    """
    from datetime import datetime, timedelta

    start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    # Always exactly 7 days from start
    dates_in_window = [
        (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(7)
    ]

    window_meals = [
        m for m in all_meals
        if m.get('timestamp', '')[:10] in dates_in_window
        or m.get('date', '') in dates_in_window
    ]

    all_plants      = set()
    bacteria_fed    = {}
    bacteria_harmed = {}
    gut_scores      = []
    daily_data      = {}

    # Initialise all 7 days
    for d in dates_in_window:
        daily_data[d] = {
            'date':            d,
            'meals':           [],
            'daily_gut_score': 0,
            'plant_count':     0
        }

    for meal in window_meals:
        date  = meal.get('timestamp', meal.get('date', ''))[:10]
        score = meal.get('overall_gut_score', 0)

        if date in daily_data:
            daily_data[date]['meals'].append(meal)

        if score:
            gut_scores.append(score)

        for food in meal.get('foods', []):
            food_name = food.get('name', '').lower().strip()
            if food_name:
                all_plants.add(food_name)

            for b in food.get('bacteria_fed', []):
                bname    = b.get('name', b) if isinstance(b, dict) else b
                strength = b.get('impact_strength', 5) \
                           if isinstance(b, dict) else 5
                if bname not in bacteria_fed:
                    bacteria_fed[bname] = {
                        'count':          0,
                        'total_strength': 0,
                        'avg_strength':   0,
                        'from_foods':     []
                    }
                bacteria_fed[bname]['count']          += 1
                bacteria_fed[bname]['total_strength'] += strength
                if food_name and food_name not in \
                        bacteria_fed[bname]['from_foods']:
                    bacteria_fed[bname]['from_foods'].append(food_name)

            for b in food.get('bacteria_harmed', []):
                bname = b.get('name', b) if isinstance(b, dict) else b
                if bname not in bacteria_harmed:
                    bacteria_harmed[bname] = {
                        'count': 0, 'from_foods': []
                    }
                bacteria_harmed[bname]['count'] += 1
                if food_name and food_name not in \
                        bacteria_harmed[bname]['from_foods']:
                    bacteria_harmed[bname]['from_foods'].append(food_name)

    # Build daily scorecards
    daily_scorecards = []
    for d in dates_in_window:
        day_meals  = daily_data[d]['meals']
        day_scores = [m.get('overall_gut_score', 0)
                      for m in day_meals if m.get('overall_gut_score')]
        day_avg    = round(sum(day_scores) / len(day_scores), 1) \
                     if day_scores else 0
        daily_scorecards.append({
            'date':            d,
            'daily_gut_score': day_avg,
            'meal_count':      len(day_meals)
        })

    # Avg strength
    for name, data in bacteria_fed.items():
        if data['count'] > 0:
            data['avg_strength'] = round(
                data['total_strength'] / data['count'], 1
            )

    sorted_bacteria = dict(
        sorted(bacteria_fed.items(),
               key=lambda x: x[1]['count'], reverse=True)
    )

    # avg_score = round(sum(gut_scores) / len(gut_scores), 1) \
    #             if gut_scores else 0
    avg_score = weighted_meal_score(window_meals)
    
    scores_only = [d['daily_gut_score']
                   for d in daily_scorecards
                   if d['daily_gut_score'] > 0]

    return {
        'week_start':       week_start,
        'dates':            dates_in_window,
        'avg_gut_score':    avg_score,
        'total_meals':      len(window_meals),
        'daily_scorecards': daily_scorecards,
        'bacteria_fed':     sorted_bacteria,
        'bacteria_harmed':  bacteria_harmed,
        'plant_diversity':  sorted(list(all_plants)),
        'plant_count':      len(all_plants),
        'best_day_score':   max(scores_only) if scores_only else 0,
        'worst_day_score':  min(scores_only) if scores_only else 0,
        'best_day':         True if scores_only else False,
    }
    
def build_monthly_gut_scorecard(all_meals, year, month):
    """
    Aggregates gut meals for a full month into a monthly report.
    """
    from datetime import datetime
    import calendar

    days_in_month = calendar.monthrange(year, month)[1]
    month_str     = f"{year}-{month:02d}"

    month_meals = [
        m for m in all_meals
        if m.get('timestamp', '').startswith(month_str)
        or m.get('date', '').startswith(month_str)
    ]

    all_plants_month    = set()
    all_bacteria_fed    = {}
    all_bacteria_harmed = {}
    gut_scores          = []
    food_frequency      = {}
    fried_count         = 0

    for meal in month_meals:
        score = meal.get('overall_gut_score', 0)
        if score:
            gut_scores.append(score)

        for food in meal.get('foods', []):
            food_name = food.get('name', '').lower().strip()
            if food_name:
                all_plants_month.add(food_name)
                food_frequency[food_name] = food_frequency.get(food_name, 0) + 1

            if food.get('cooking_method', '') == 'fried':
                fried_count += 1

            # ── Bacteria fed ──────────────────────────────
            for b in food.get('bacteria_fed', []):
                bname    = b.get('name', b) if isinstance(b, dict) else b
                strength = b.get('impact_strength', 5) \
                           if isinstance(b, dict) else 5
                if bname not in all_bacteria_fed:
                    all_bacteria_fed[bname] = {
                        'count':          0,
                        'total_strength': 0,
                        'avg_strength':   0,
                        'from_foods':     []
                    }
                all_bacteria_fed[bname]['count']          += 1
                all_bacteria_fed[bname]['total_strength'] += strength
                if food_name and food_name not in \
                        all_bacteria_fed[bname]['from_foods']:
                    all_bacteria_fed[bname]['from_foods'].append(food_name)

            # ── Bacteria harmed ───────────────────────────
            for b in food.get('bacteria_harmed', []):
                bname = b.get('name', b) if isinstance(b, dict) else b
                if bname not in all_bacteria_harmed:
                    all_bacteria_harmed[bname] = {
                        'count':      0,
                        'from_foods': []
                    }
                all_bacteria_harmed[bname]['count'] += 1
                if food_name and food_name not in \
                        all_bacteria_harmed[bname]['from_foods']:
                    all_bacteria_harmed[bname]['from_foods'].append(food_name)

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

    avg_score = weighted_meal_score(month_meals)

    return {
        'year':            year,
        'month':           month,
        'month_str':       month_str,
        'avg_gut_score':   avg_score,
        'total_meals':     len(month_meals),
        'bacteria_fed':    sorted_bacteria,
        'bacteria_harmed': all_bacteria_harmed,
        'plant_diversity': sorted(list(all_plants_month)),
        'plant_count':     len(all_plants_month),
        'top_foods':       top_foods,
        'fried_meals':     fried_count,
        'gut_scores':      gut_scores,
    }
    # ── Profile functions to ADD to gut_engine.py ────────────────────────────────

def get_empty_profile(patient_id='guest'):
    return {
        "patient_id":    patient_id,
        "name":          "",
        "test_date":     "",
        "test_provider": "",
        "doctor":        "",
        "metrics": {
            "evenness":  0,
            "diversity": 0,
            "fb_ratio":  0
        },
        "functions": {
            "overall_health":    {"helpful": 0, "harmful": 0},
            "immunity":          {"helpful": 0, "harmful": 0},
            "gi_health":         {"helpful": 0, "harmful": 0},
            "mental_wellness":   {"helpful": 0, "harmful": 0},
            "weight_management": {"helpful": 0, "harmful": 0},
            "sugar_metabolism":  {"helpful": 0, "harmful": 0}
        },
        "bacteria_boost":  [],
        "bacteria_reduce": [],
        "foods_add":       [],
        "foods_reduce":    [],
        "food_targets":    []
    }


def load_gut_profile(patient_id='guest'):
    """Load patient gut profile from file"""
    profile_file = 'gut_patient_profile.json'
    if not os.path.exists(profile_file):
        return get_empty_profile(patient_id)
    try:
        with open(profile_file, 'r') as f:
            data = json.load(f)

        # Handle list of profiles
        if isinstance(data, list):
            for p in data:
                if p.get('patient_id') == patient_id:
                    return p
            return get_empty_profile(patient_id)

        # Handle single dict (legacy) — migrate to list
        elif isinstance(data, dict):
            if data.get('patient_id') == patient_id:
                return data
            # Not this patient's profile
            return get_empty_profile(patient_id)

    except Exception:
        return get_empty_profile(patient_id)


def save_gut_profile(profile_data):
    """Save patient gut profile — preserves other patients."""
    profile_file = 'gut_patient_profile.json'
    patient_id   = profile_data.get('patient_id', 'guest')

    # Load existing data
    existing = []
    if os.path.exists(profile_file):
        try:
            with open(profile_file, 'r') as f:
                data = json.load(f)
            # Convert single dict to list
            if isinstance(data, dict):
                existing = [data]
            elif isinstance(data, list):
                existing = data
        except Exception:
            existing = []

    # Update or insert this patient's profile
    found = False
    for i, p in enumerate(existing):
        if p.get('patient_id') == patient_id:
            existing[i] = profile_data
            found = True
            break

    if not found:
        existing.append(profile_data)

    # Save all profiles
    with open(profile_file, 'w') as f:
        json.dump(existing, f, indent=2)


def delete_gut_profile(patient_id):
    """
    Remove this patient's profile entirely so they see the
    empty/template-selection screen again on next load.
    Other patients' profiles are untouched.
    """
    profile_file = 'gut_patient_profile.json'
    if not os.path.exists(profile_file):
        return True

    try:
        with open(profile_file, 'r') as f:
            data = json.load(f)
    except Exception:
        return False

    if isinstance(data, dict):
        existing = [data]
    elif isinstance(data, list):
        existing = data
    else:
        existing = []

    remaining = [p for p in existing if p.get('patient_id') != patient_id]

    with open(profile_file, 'w') as f:
        json.dump(remaining, f, indent=2)

    return True


def check_food_targets_today(patient_profile, meals_today):
    """
    Compare doctor-prescribed food targets against what patient ate today.
    Returns list of progress dicts per target food.
    """
    targets  = patient_profile.get('food_targets', [])
    progress = []

    for target in targets:
        food_name    = target.get('food', '').lower().strip()
        target_grams = target.get('amount_grams', 0)
        eaten_grams  = 0
        eaten_meals  = []

        for meal in meals_today:
            for food in meal.get('foods', []):
                name = food.get('name', '').lower().strip()
                if food_name in name or name in food_name or \
                   any(w in name for w in food_name.split() if len(w) > 3):
                    grams = food.get('estimated_grams', 0)
                    eaten_grams += grams
                    eaten_meals.append(meal.get('timestamp', '')[:5])

        pct    = min(100, round(eaten_grams / target_grams * 100)) \
                 if target_grams > 0 else 0
        status = 'met' if pct >= 90 else 'partial' if pct >= 50 else 'missed'

        progress.append({
            "food":         target.get('food', ''),
            "target_grams": target_grams,
            "eaten_grams":  round(eaten_grams, 1),
            "pct":          pct,
            "status":       status,
            "frequency":    target.get('frequency', 'daily'),
            "feeds":        target.get('feeds', ''),
            "alternatives": target.get('alternatives', []),
            "eaten_at":     eaten_meals
        })

    return progress


def check_bacteria_progress_today(patient_profile, meals_today):
    """
    Check which bacteria from the boost list were fed today.
    Returns progress per bacteria target.
    """
    bacteria_boost = patient_profile.get('bacteria_boost', [])
    progress       = []

    for target_bact in bacteria_boost:
        target_name = target_bact.get('name', '').lower().strip()
        fed_count   = 0
        fed_by      = []
        strength    = 0

        for meal in meals_today:
            for food in meal.get('foods', []):
                for b in food.get('bacteria_fed', []):
                    b_name = (b.get('name', b)
                              if isinstance(b, dict) else b).lower().strip()
                    # Match on genus name (first word)
                    t_genus = target_name.split()[0]
                    b_genus = b_name.split()[0]
                    if t_genus in b_genus or b_genus in t_genus:
                        fed_count += 1
                        fed_by.append(food.get('name', ''))
                        if isinstance(b, dict):
                            strength = max(strength,
                                          b.get('impact_strength', 0))

        progress.append({
            "name":      target_bact.get('name', ''),
            "level":     target_bact.get('level', 'low'),
            "functions": target_bact.get('functions', []),
            "fed_today": fed_count > 0,
            "fed_count": fed_count,
            "fed_by":    list(set(fed_by)),
            "strength":  strength
        })

    return progress

def analyse_full_day_with_claude(day_meals, patient_profile):
    """
    Send entire day's food log to Claude for holistic gut analysis.
    Returns structured JSON with sequencing, FODMAP load, bacteria
    net effect and tomorrow's priorities.
    """
    import os, json, requests

    CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY"}

    if not day_meals:
        return {"error": "No meals to analyse"}

    # ── Build chronological food log for Claude ───────────────────────────
    day_log_lines = []
    for meal in sorted(day_meals, key=lambda x: x.get('timestamp', '')):
        time  = meal.get('timestamp', '')[-5:] or 'Unknown time'
        foods = meal.get('foods', [])
        food_list = ', '.join(
            f"{f.get('name','?')} ({f.get('estimated_grams',0)}g)"
            for f in foods
        )
        score = meal.get('overall_gut_score', 0)
        day_log_lines.append(
            f"  {time}: {food_list} [meal score: {score}/10]"
        )

    day_log = '\n'.join(day_log_lines)

    # ── Extract profile data ───────────────────────────────────────────────
    bacteria_boost = ', '.join(
        b.get('name', '') for b in
        patient_profile.get('bacteria_boost', [])
    ) or 'Not specified'

    bacteria_reduce = ', '.join(
        b.get('name', '') for b in
        patient_profile.get('bacteria_reduce', [])
    ) or 'Not specified'

    food_targets = ', '.join(
        f"{t.get('food','')} {t.get('amount_grams',0)}g {t.get('frequency','')}"
        for t in patient_profile.get('food_targets', [])
    ) or 'Not specified'

    # ── Build prompt ──────────────────────────────────────────────────────
    prompt = DAILY_ANALYSIS_PROMPT.format(
        bacteria_boost  = bacteria_boost,
        bacteria_reduce = bacteria_reduce,
        food_targets    = food_targets,
        day_log         = day_log
    )

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 1500,
                "messages": [{
                    "role":    "user",
                    "content": prompt
                }]
            },
            timeout=30
        )

        if response.status_code != 200:
            return {"error": f"Claude error {response.status_code}"}

        # text = response.json()['content'][0]['text'].strip()

        # # Strip markdown if present
        # if '```' in text:
        #     text = text.split('```')[1]
        #     if text.startswith('json'):
        #         text = text[4:]
        #     text = text.split('```')[0]

        # return json.loads(text.strip())

        text = response.json()['content'][0]['text'].strip()

        # Debug — see what Claude returned
        print(f'[daily_analysis] Raw response: {text[:200]}')

        # Strip markdown code fences robustly
        if '```' in text:
            # Extract content between first ``` and last ```
            parts = text.split('```')
            # parts[1] is the content inside the fences
            if len(parts) >= 3:
                text = parts[1]
            else:
                text = parts[1] if len(parts) > 1 else text
            # Remove language identifier (json, python etc)
            if text.startswith('json'):
                text = text[4:]
            elif text.startswith('JSON'):
                text = text[4:]
            text = text.strip()

        # Find JSON object — start from first {
        start = text.find('{')
        end   = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]

        print(f'[daily_analysis] Cleaned JSON: {text[:100]}')
        return json.loads(text)

    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"error": f"Analysis failed: {e}"}


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND — Add to gut_engine.py
# ══════════════════════════════════════════════════════════════════════════════
def find_previous_food_analysis(all_meals, food_name):
    """
    Find the most recent analysis of a specific food.
    Returns (food_dict, meal_dict) or (None, None).
    """
    search = food_name.lower().strip()
    
    for meal in reversed(all_meals):  # newest first
        for food in meal.get('foods', []):
            fname = food.get('name', '').lower().strip()
            # Match if food name contains search term or vice versa
            if search in fname or fname in search:
                return food, meal
    return None, None


def build_instant_meal(patient_id, food, previous_meal, timezone_str=''):
    """
    Build a new meal entry reusing previous food analysis.
    """
    from datetime import datetime, timezone, timedelta

    # Get current timestamp
    try:
        if timezone_str:
            # Simple offset approach — no pytz needed
            now = datetime.now()
        else:
            now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M')
    except Exception:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

    date = timestamp[:10]

    # Calculate score from this single food
    pre   = food.get('prebiotic_score', 0)
    anti  = food.get('anti_inflammatory_score', 0)
    score = round((pre + anti) / 2, 1) if (pre or anti) else 5.0

    return {
        "patient_id":        patient_id,
        "timestamp":         timestamp,
        "date":              date,
        "meal_description":  food.get('name', 'Quick logged meal'),
        "foods":             [food],
        "gut_scores":        {
            "prebiotic_score":         pre,
            "anti_inflammatory_score": anti,
        },
        "overall_gut_score": score,
        "gut_notes":         f"Quick logged — same as previous {food.get('name','')}",
        "quick_logged":      True,
    }