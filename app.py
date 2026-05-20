# Food Analyzer - Flask Web App
# Author: Sanyam
# Version: 3.0 - Claude Vision + Gut Bacteria + AFCD Verification
# Started: May 2026

import os
import re
import json
import math
from io import BytesIO
from base64 import b64decode, b64encode

try:
    from PIL import Image
except Exception:
    Image = None

import requests
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, g
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
AI_PROVIDER    = os.getenv("AI_PROVIDER", "claude").lower()

print("DEBUG: GEMINI_API_KEY:", "YES" if GEMINI_API_KEY else "NO")
print("DEBUG: CLAUDE_API_KEY:", "YES" if CLAUDE_API_KEY else "NO")
print("DEBUG: AI_PROVIDER:", AI_PROVIDER)

app = Flask(__name__)

# ─── Logging ─────────────────────────────────────────
def request_log(msg):
    try:
        if not hasattr(g, 'request_log'):
            g.request_log = []
        g.request_log.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
    except Exception:
        print("LOG:", msg)

# ─── DB helpers ───────────────────────────────────────
def get_db():
    conn = sqlite3.connect('food_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def normalize_text(text):
    if not text:
        return ''
    cleaned = re.sub(r'[^a-z0-9 ]+', ' ', text.lower())
    return re.sub(r'\s+', ' ', cleaned).strip()

def cosine_similarity(a, b):
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0

def get_query_embedding(text):
    """Get Gemini embedding for a search query"""
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={GEMINI_API_KEY}'
    r = requests.post(url, json={
        'model': 'models/gemini-embedding-2',
        'content': {'parts': [{'text': text.lower()}]}
    })
    if r.status_code == 200:
        return r.json()['embedding']['values']
    request_log(f"Embedding error {r.status_code} for '{text}'")
    return None

NUTRITION_SELECT = """
    SELECT food_key, food_name, energy_kcal,
           COALESCE(protein, 0)       as protein,
           COALESCE(fat, 0)           as fat,
           COALESCE(carbohydrates, 0) as carbohydrates,
           COALESCE(fibre, 0)         as fibre,
           COALESCE(sugars, 0)        as sugars,
           COALESCE(sodium, 0)        as sodium,
           COALESCE(calcium, 0)       as calcium,
           COALESCE(iron, 0)          as iron,
           COALESCE(magnesium, 0)     as magnesium,
           COALESCE(potassium, 0)     as potassium,
           COALESCE(zinc, 0)          as zinc,
           COALESCE(vitamin_a, 0)     as vitamin_a,
           COALESCE(vitamin_c, 0)     as vitamin_c,
           COALESCE(vitamin_d, 0)     as vitamin_d,
           COALESCE(vitamin_e, 0)     as vitamin_e,
           COALESCE(cholesterol, 0)   as cholesterol
    FROM foods_afcd
"""

def search_afcd_by_embedding(food_name, threshold=0.82):
    """
    Search AFCD using semantic embeddings.
    Returns best match if score >= threshold, else None.
    """
    if not GEMINI_API_KEY:
        return None, 0.0

    query_vec = get_query_embedding(food_name)
    if not query_vec:
        return None, 0.0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT food_key, food_name, energy_kcal, embedding
        FROM foods_afcd
        WHERE embedding IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()

    best_score = 0.0
    best_key   = None

    for row in rows:
        try:
            vec   = json.loads(row['embedding'])
            score = cosine_similarity(query_vec, vec)
            if score > best_score:
                best_score = score
                best_key   = row['food_key']
        except Exception:
            continue

    request_log(f"Embedding search '{food_name}' → score={best_score:.3f} key={best_key}")

    if best_score >= threshold:
        return best_key, best_score
    return None, best_score

def get_nutrition_by_key(food_key):
    """Get full nutrition row by AFCD food key"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(NUTRITION_SELECT + " WHERE food_key = ? LIMIT 1", (food_key,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None

# ─── Claude Vision ────────────────────────────────────
CLAUDE_VISION_PROMPT = """You are an expert clinical nutritionist and gut microbiome specialist.

Analyse this food image carefully and return complete nutritional and gut health data.

RULES:
1. Identify EVERY distinct food item on the plate
2. Use specific names: "Banana, cavendish, raw" not just "banana"
3. Estimate weight in grams based on visual portion size
4. Provide accurate nutrition data per 100g from your knowledge
5. For gut bacteria: base on scientific literature about food-microbiome interactions
6. confidence: "high" if clearly visible, "medium" if partially visible, "low" if uncertain

Respond ONLY in this exact JSON format, no other text:
{
  "foods": [
    {
      "name": "specific food name",
      "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|not applicable",
      "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
      "estimated_grams": 100,
      "confidence": "high|medium|low",
      "nutrition_per_100g": {
        "calories_kcal": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbohydrates_g": 0,
        "fibre_g": 0,
        "sugar_g": 0,
        "sodium_mg": 0,
        "calcium_mg": 0,
        "iron_mg": 0,
        "magnesium_mg": 0,
        "potassium_mg": 0,
        "zinc_mg": 0,
        "vitamin_a_ug": 0,
        "vitamin_c_mg": 0,
        "vitamin_d_ug": 0,
        "vitamin_e_mg": 0,
        "cholesterol_mg": 0
      },
      "gut_microbiome": {
        "prebiotic_score": 0,
        "probiotic_score": 0,
        "bacteria_promoted": [],
        "bacteria_reduced": [],
        "fibre_type": "soluble|insoluble|both|none",
        "gut_health_notes": "brief clinical note"
      }
    }
  ],
  "meal_description": "brief description",
  "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
  "overall_gut_health_score": 0,
  "overall_gut_notes": "overall gut health summary for this meal"
}"""

def analyze_with_claude_vision(image_base64, mime_type="image/jpeg"):
    """Analyze food image using Claude - returns full nutrition + gut bacteria data"""
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY in .env file"}

    request_log("Calling Claude Vision API")

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json"
        },
        json={
            "model":      "claude-sonnet-4-6",
            "max_tokens": 4000,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": mime_type,
                            "data":       image_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": CLAUDE_VISION_PROMPT
                    }
                ]
            }]
        }
    )

    request_log(f"Claude status: {response.status_code}")

    if response.status_code != 200:
        return {"error": f"Claude API error {response.status_code}: {response.text[:200]}"}

    try:
        text = response.json()['content'][0]['text'].strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed to parse Claude response: {e}"}

def analyze_with_claude_voice(voice_text):
    """Extract food items from voice text using Claude"""
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY in .env file"}

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json"
        },
        json={
            "model":      "claude-sonnet-4-6",
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": f"""You are a clinical nutritionist and gut microbiome specialist.

Extract food items from this text: "{voice_text}"

For each food, provide complete nutrition and gut health data.

Respond ONLY in this exact JSON format:
{{
  "foods": [
    {{
      "name": "specific food name",
      "cooking_method": "raw|grilled|fried|boiled|steamed|not applicable",
      "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment",
      "estimated_grams": 100,
      "confidence": "high|medium|low",
      "nutrition_per_100g": {{
        "calories_kcal": 0,
        "protein_g": 0,
        "fat_g": 0,
        "carbohydrates_g": 0,
        "fibre_g": 0,
        "sugar_g": 0,
        "sodium_mg": 0,
        "calcium_mg": 0,
        "iron_mg": 0,
        "magnesium_mg": 0,
        "potassium_mg": 0,
        "zinc_mg": 0,
        "vitamin_a_ug": 0,
        "vitamin_c_mg": 0,
        "vitamin_d_ug": 0,
        "vitamin_e_mg": 0,
        "cholesterol_mg": 0
      }},
      "gut_microbiome": {{
        "prebiotic_score": 0,
        "probiotic_score": 0,
        "bacteria_promoted": [],
        "bacteria_reduced": [],
        "fibre_type": "soluble|insoluble|both|none",
        "gut_health_notes": "brief clinical note"
      }}
    }}
  ],
  "meal_description": "brief description",
  "overall_gut_health_score": 0,
  "overall_gut_notes": "overall gut health summary"
}}"""
            }]
        }
    )

    if response.status_code != 200:
        return {"error": f"Claude API error {response.status_code}"}

    try:
        text = response.json()['content'][0]['text'].strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed to parse Claude response: {e}"}

def analyze_with_gemini_vision(image_base64, mime_type="image/jpeg"):
    """Fallback: Gemini vision (no nutrition data, uses AFCD only)"""
    if not GEMINI_API_KEY:
        return {"error": "Missing GEMINI_API_KEY in .env file"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                {"text": """Analyze this food image. Identify each food item.
Respond ONLY in this JSON format:
{
  "foods": [
    {
      "name": "specific food name",
      "cooking_method": "raw|grilled|fried|boiled|steamed|not applicable",
      "category": "protein|grain|vegetable|fruit|dairy|sauce",
      "estimated_grams": 100,
      "confidence": "high|medium|low",
      "nutrition_per_100g": null,
      "gut_microbiome": null
    }
  ],
  "meal_description": "brief description",
  "overall_gut_health_score": null,
  "overall_gut_notes": null
}"""}
            ]
        }]
    }
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        return {"error": f"Gemini error {response.status_code}"}
    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed to parse Gemini response: {e}"}

# ─── Nutrition builder ────────────────────────────────
def build_food_entry(food, grams, nutrition_source, afcd_data=None, afcd_score=0.0):
    """
    Build final food entry merging Claude estimates with AFCD verified data.
    afcd_data overrides Claude if score is high enough.
    """
    n = food.get('nutrition_per_100g') or {}
    gut = food.get('gut_microbiome') or {}

    # Use AFCD data if good match found
    if afcd_data and afcd_score >= 0.82:
        source = f"AFCD verified ({afcd_score:.2f})"
        cal  = afcd_data.get('energy_kcal', 0)
        prot = afcd_data.get('protein', 0)
        fat  = afcd_data.get('fat', 0)
        carb = afcd_data.get('carbohydrates', 0)
        fibr = afcd_data.get('fibre', 0)
        sugr = afcd_data.get('sugars', 0)
        sod  = afcd_data.get('sodium', 0)
        cal_ = afcd_data.get('calcium', 0)
        ir   = afcd_data.get('iron', 0)
        mag  = afcd_data.get('magnesium', 0)
        pot  = afcd_data.get('potassium', 0)
        zn   = afcd_data.get('zinc', 0)
        va   = afcd_data.get('vitamin_a', 0)
        vc   = afcd_data.get('vitamin_c', 0)
        vd   = afcd_data.get('vitamin_d', 0)
        ve   = afcd_data.get('vitamin_e', 0)
        chol = afcd_data.get('cholesterol', 0)
        matched_name = afcd_data.get('food_name', food['name'])
    else:
        source = "Claude AI estimated"
        cal  = n.get('calories_kcal', 0)
        prot = n.get('protein_g', 0)
        fat  = n.get('fat_g', 0)
        carb = n.get('carbohydrates_g', 0)
        fibr = n.get('fibre_g', 0)
        sugr = n.get('sugar_g', 0)
        sod  = n.get('sodium_mg', 0)
        cal_ = n.get('calcium_mg', 0)
        ir   = n.get('iron_mg', 0)
        mag  = n.get('magnesium_mg', 0)
        pot  = n.get('potassium_mg', 0)
        zn   = n.get('zinc_mg', 0)
        va   = n.get('vitamin_a_ug', 0)
        vc   = n.get('vitamin_c_mg', 0)
        vd   = n.get('vitamin_d_ug', 0)
        ve   = n.get('vitamin_e_mg', 0)
        chol = n.get('cholesterol_mg', 0)
        matched_name = food['name']

    def p(v): return round((v or 0) * grams / 100, 2)

    return {
        "name":             food['name'],
        "matched":          matched_name,
        "grams":            grams,
        "confidence":       food.get('confidence', 'medium'),
        "cooking_method":   food.get('cooking_method', ''),
        "category":         food.get('category', ''),
        "data_source":      source,
        "afcd_score":       round(afcd_score, 3),
        "found_in_db":      afcd_data is not None and afcd_score >= 0.82,
        # Calculated nutrition
        "calories":         p(cal),
        "protein":          p(prot),
        "fat":              p(fat),
        "carbs":            p(carb),
        "fibre":            p(fibr),
        "sugars":           p(sugr),
        "sodium":           p(sod),
        "calcium":          p(cal_),
        "iron":             p(ir),
        "magnesium":        p(mag),
        "potassium":        p(pot),
        "zinc":             p(zn),
        "vitamin_a":        p(va),
        "vitamin_c":        p(vc),
        "vitamin_d":        p(vd),
        "vitamin_e":        p(ve),
        "cholesterol":      p(chol),
        # Gut microbiome data from Claude
        "gut_microbiome": {
            "prebiotic_score":   gut.get('prebiotic_score', 0),
            "probiotic_score":   gut.get('probiotic_score', 0),
            "bacteria_promoted": gut.get('bacteria_promoted', []),
            "bacteria_reduced":  gut.get('bacteria_reduced', []),
            "fibre_type":        gut.get('fibre_type', 'none'),
            "gut_health_notes":  gut.get('gut_health_notes', '')
        }
    }

def calculate_nutrition(ai_result):
    """Process AI result, verify against AFCD, build final entries"""
    foods_out    = []
    total_cal    = 0

    for food in ai_result.get('foods', []):
        grams     = food.get('estimated_grams', 100) or 100
        food_name = food.get('name', '')

        request_log(f"Processing '{food_name}' ({grams}g)")

        # Try AFCD embedding verification
        afcd_key, afcd_score = search_afcd_by_embedding(food_name)
        afcd_data = get_nutrition_by_key(afcd_key) if afcd_key else None

        if afcd_data:
            request_log(f"AFCD match: {afcd_data['food_name']} (score={afcd_score:.3f})")
        else:
            request_log(f"No AFCD match above threshold, using Claude estimate")

        entry = build_food_entry(food, grams, "claude", afcd_data, afcd_score)
        foods_out.append(entry)
        total_cal += entry['calories']

    return foods_out, round(total_cal, 1)

# ─── Image resize ─────────────────────────────────────
def resize_image(image_base64):
    if Image is None:
        return image_base64
    try:
        img_data = b64decode(image_base64)
        img = Image.open(BytesIO(img_data))
        orig_w, orig_h = img.size
        max_w, max_h = 1200, 900
        ratio = min(max_w / orig_w, max_h / orig_h, 1)
        if ratio < 1:
            tw = max(1, int(orig_w * ratio))
            th = max(1, int(orig_h * ratio))
            img = img.convert('RGB').resize((tw, th), Image.LANCZOS)
            out = BytesIO()
            img.save(out, format='JPEG', quality=80)
            request_log(f"Resized {orig_w}x{orig_h} → {tw}x{th}")
            return b64encode(out.getvalue()).decode('ascii')
    except Exception as e:
        request_log(f"Resize failed: {e}")
    return image_base64

# ─── Routes ──────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data         = request.get_json()
        g.request_log = []
        request_log("Received /analyze request")

        image_base64 = data.get('image')
        mime_type    = data.get('mime_type', 'image/jpeg')
        provider     = data.get('provider', AI_PROVIDER).lower()

        request_log(f"Provider: {provider}")

        # Resize image
        image_base64 = resize_image(image_base64)

        # Analyze with chosen provider
        if provider == 'gemini':
            ai_result = analyze_with_gemini_vision(image_base64, mime_type)
        else:
            ai_result = analyze_with_claude_vision(image_base64, mime_type)

        if isinstance(ai_result, dict) and ai_result.get('error'):
            return jsonify({"error": ai_result['error']}), 500

        foods, total_calories = calculate_nutrition(ai_result)

        result = {
            "meal_description":        ai_result.get('meal_description', ''),
            "cuisine_type":            ai_result.get('cuisine_type', 'Unknown'),
            "overall_gut_health_score": ai_result.get('overall_gut_health_score', 0),
            "overall_gut_notes":       ai_result.get('overall_gut_notes', ''),
            "foods":                   foods,
            "total_calories":          total_calories,
            "timestamp":               datetime.now().strftime("%Y-%m-%d %H:%M"),
            "debug_log":               g.request_log
        }

        save_meal_log(result)
        return jsonify(result)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/analyze-voice', methods=['POST'])
def analyze_voice():
    try:
        data         = request.get_json()
        g.request_log = []
        request_log("Received /analyze-voice request")

        voice_text = data.get('text', '')
        provider   = data.get('provider', AI_PROVIDER).lower()

        request_log(f"Provider: {provider}, text length: {len(voice_text)}")

        if provider == 'gemini':
            # Gemini voice fallback
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": f'Extract foods from: "{voice_text}". Return JSON: {{"foods":[{{"name":"food","estimated_grams":100,"confidence":"high","nutrition_per_100g":null,"gut_microbiome":null}}],"meal_description":"","overall_gut_health_score":null,"overall_gut_notes":null}}'}]}]}
            r = requests.post(url, json=payload)
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if "```" in text:
                text = text.split("```")[1][4:] if text.split("```")[1].startswith("json") else text.split("```")[1]
            ai_result = json.loads(text.strip())
        else:
            ai_result = analyze_with_claude_voice(voice_text)

        if isinstance(ai_result, dict) and ai_result.get('error'):
            return jsonify({"error": ai_result['error']}), 500

        foods, total_calories = calculate_nutrition(ai_result)

        result = {
            "meal_description":         ai_result.get('meal_description', ''),
            "overall_gut_health_score": ai_result.get('overall_gut_health_score', 0),
            "overall_gut_notes":        ai_result.get('overall_gut_notes', ''),
            "foods":                    foods,
            "total_calories":           total_calories,
            "timestamp":                datetime.now().strftime("%Y-%m-%d %H:%M"),
            "debug_log":                g.request_log
        }

        save_meal_log(result)
        return jsonify(result)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def history():
    try:
        if os.path.exists('meals_log.json'):
            with open('meals_log.json', 'r') as f:
                log = json.load(f)
            return jsonify(log[-10:])
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/recalculate', methods=['POST'])
def recalculate():
    """Recalculate nutrition when user edits grams"""
    try:
        data  = request.get_json() or {}
        foods = data.get('foods', [])

        recalculated = []
        for item in foods:
            name  = str(item.get('name', '') or '').strip()
            try:
                grams = float(item.get('grams', 0) or 0)
            except Exception:
                grams = 0

            afcd_key, afcd_score = search_afcd_by_embedding(name)
            afcd_data = get_nutrition_by_key(afcd_key) if afcd_key else None

            # Rebuild entry preserving gut data from original
            fake_food = {
                "name":             name,
                "confidence":       item.get('confidence', 'medium'),
                "cooking_method":   item.get('cooking_method', ''),
                "category":         item.get('category', ''),
                "nutrition_per_100g": None,
                "gut_microbiome":   item.get('gut_microbiome', {})
            }
            entry = build_food_entry(fake_food, grams, "claude", afcd_data, afcd_score)
            recalculated.append(entry)

        return jsonify({'foods': recalculated})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def save_meal_log(meal_data):
    log_file = 'meals_log.json'
    log = []
    if os.path.exists(log_file):
        with open(log_file, 'r') as f:
            log = json.load(f)
    log.append(meal_data)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
