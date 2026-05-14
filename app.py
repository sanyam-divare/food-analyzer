# Food Analyzer - Flask Web App
# Author: Sanyam
# Started: May 2026

import os
import json
import requests
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)

# ─── Database ────────────────────────────────────────
def get_db():
    conn = sqlite3.connect('food_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def search_food(food_name):
    try:
        conn = get_db()
        cursor = conn.cursor()

        query = """
            SELECT food_name, energy_kcal,
                   COALESCE(protein, 0) as protein,
                   COALESCE(fat, 0) as fat,
                   COALESCE(carbohydrates, 0) as carbohydrates,
                   COALESCE(fibre, 0) as fibre,
                   COALESCE(sodium, 0) as sodium,
                   COALESCE(calcium, 0) as calcium,
                   COALESCE(iron, 0) as iron,
                   COALESCE(magnesium, 0) as magnesium,
                   COALESCE(potassium, 0) as potassium,
                   COALESCE(zinc, 0) as zinc,
                   COALESCE(vitamin_a, 0) as vitamin_a,
                   COALESCE(vitamin_c, 0) as vitamin_c,
                   COALESCE(vitamin_d, 0) as vitamin_d,
                   COALESCE(vitamin_e, 0) as vitamin_e,
                   COALESCE(cholesterol, 0) as cholesterol,
                   COALESCE(sugars, 0) as sugars
            FROM foods_afcd
            WHERE LOWER(food_name) LIKE ?
            ORDER BY LENGTH(food_name) ASC
            LIMIT 1
        """

        # Try exact word match first (highest priority)
        cursor.execute(query, (f'%{food_name.lower()}%',))
        result = cursor.fetchone()

        # Try individual words if no match
        if not result:
            words = food_name.lower().split()
            for word in words:
                if len(word) > 3:
                    cursor.execute(query, (f'%{word}%',))
                    result = cursor.fetchone()
                    if result:
                        break

        # Fallback to manual foods table
        if not result:
            cursor.execute("""
                SELECT food_name, energy_kcal,
                       COALESCE(protein, 0) as protein,
                       COALESCE(fat, 0) as fat,
                       COALESCE(carbohydrates, 0) as carbohydrates,
                       0 as fibre, 0 as sodium, 0 as calcium,
                       0 as iron, 0 as magnesium, 0 as potassium,
                       0 as zinc, 0 as vitamin_a, 0 as vitamin_c,
                       0 as vitamin_d, 0 as vitamin_e,
                       0 as cholesterol, 0 as sugars
                FROM foods
                WHERE LOWER(food_name) LIKE ?
                LIMIT 1
            """, (f'%{food_name.lower()}%',))
            result = cursor.fetchone()

        conn.close()
        return dict(result) if result else None

    except Exception as e:
        print(f"DB search error for '{food_name}': {e}")
        return None

# ─── Gemini AI ───────────────────────────────────────
def analyze_with_gemini(image_base64, mime_type="image/jpeg"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                {"text": """Analyze this food image. List each food item you see.
                    Respond ONLY in this exact JSON format, no other text:
                    {
                        "foods": [
                            {"name": "food name", "estimated_grams": 100}
                        ],
                        "meal_description": "brief description"
                    }"""}
            ]
        }]
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    return None

# ─── Nutrition calculator ─────────────────────────────

def calculate_nutrition(ai_result):
    foods_with_nutrition = []
    total_calories = 0

    for food in ai_result['foods']:
        g = food['estimated_grams']
        food_name = food['name']

        print(f"DEBUG: Looking up '{food_name}' ({g}g)")

        # Step 1 — get candidates
        candidates = get_candidates(food_name)
        print(f"DEBUG: Found {len(candidates)} candidates")

        # Step 2 — ask Gemini to pick best match
        best_key = ask_gemini_to_match(food_name, g, candidates)

        # Step 3 — get nutrition by key
        n = get_nutrition_by_key(best_key) if best_key else None

        # Fallback to old search if Gemini match fails
        if not n:
            print(f"DEBUG: Falling back to fuzzy search for '{food_name}'")
            n = search_food(food_name)

        def calc(key):
            return round((n.get(key, 0) or 0) * g / 100, 2) if n else 0

        matched_name = n['food_name'] if n else 'Not found'
        print(f"DEBUG: Final match → {matched_name}")

        entry = {
            "name":        food_name,
            "matched":     matched_name,
            "grams":       g,
            "found_in_db": n is not None,
            "calories":    calc('energy_kcal'),
            "protein":     calc('protein'),
            "fat":         calc('fat'),
            "carbs":       calc('carbohydrates'),
            "fibre":       calc('fibre'),
            "sugars":      calc('sugars'),
            "sodium":      calc('sodium'),
            "calcium":     calc('calcium'),
            "iron":        calc('iron'),
            "magnesium":   calc('magnesium'),
            "potassium":   calc('potassium'),
            "zinc":        calc('zinc'),
            "vitamin_a":   calc('vitamin_a'),
            "vitamin_c":   calc('vitamin_c'),
            "vitamin_d":   calc('vitamin_d'),
            "vitamin_e":   calc('vitamin_e'),
            "cholesterol": calc('cholesterol'),
        }
        foods_with_nutrition.append(entry)
        total_calories += entry['calories']

    return foods_with_nutrition, round(total_calories, 1)

# ─── Routes ──────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data          = request.get_json()
        image_base64  = data.get('image')
        mime_type     = data.get('mime_type', 'image/jpeg')

        ai_result = analyze_with_gemini(image_base64, mime_type)
        if not ai_result:
            return jsonify({"error": "AI analysis failed"}), 500

        foods, total_calories = calculate_nutrition(ai_result)
        result = {
            "meal_description": ai_result['meal_description'],
            "foods":            foods,
            "total_calories":   total_calories,
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M")
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
        data       = request.get_json()
        voice_text = data.get('text', '')

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"""Extract food items from this text: "{voice_text}"
                    Respond ONLY in this exact JSON format:
                    {{
                        "foods": [
                            {{"name": "food name", "estimated_grams": 100}}
                        ],
                        "meal_description": "brief description"
                    }}"""
                }]
            }]
        }

        response  = requests.post(url, json=payload)
        if response.status_code == 200:
            result = response.json()
            text   = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            ai_result = json.loads(text.strip())

            foods, total_calories = calculate_nutrition(ai_result)
            result = {
                "meal_description": ai_result['meal_description'],
                "foods":            foods,
                "total_calories":   total_calories,
                "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M")
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

def save_meal_log(meal_data):
    log_file = 'meals_log.json'
    log = []
    if os.path.exists(log_file):
        with open('meals_log.json', 'r') as f:
            log = json.load(f)
    log.append(meal_data)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)


def get_candidates(food_name):
    """Get top 15 candidates from database"""
    conn = get_db()
    cursor = conn.cursor()

    candidates = []

    # Search by full name
    cursor.execute("""
        SELECT food_key, food_name, energy_kcal
        FROM foods_afcd
        WHERE LOWER(food_name) LIKE ?
        ORDER BY LENGTH(food_name) ASC
        LIMIT 15
    """, (f'%{food_name.lower()}%',))
    candidates = cursor.fetchall()

    # Try word by word if too few results
    if len(candidates) < 3:
        words = food_name.lower().split()
        for word in words:
            if len(word) > 3:
                cursor.execute("""
                    SELECT food_key, food_name, energy_kcal
                    FROM foods_afcd
                    WHERE LOWER(food_name) LIKE ?
                    ORDER BY LENGTH(food_name) ASC
                    LIMIT 15
                """, (f'%{word}%',))
                candidates = cursor.fetchall()
                if candidates:
                    break

    conn.close()
    return [dict(c) for c in candidates]


def ask_gemini_to_match(food_name, grams, candidates):
    """Ask Gemini to pick the best matching food from candidates"""
    if not candidates:
        return None

    # Format candidates for Gemini
    candidate_list = "\n".join([
        f"- Key: {c['food_key']} | {c['food_name']} | {c['energy_kcal']} kcal/100g"
        for c in candidates
    ])

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [{
                "text": f"""I have identified "{food_name}" ({grams}g) in a food image.
From the Australian Food Composition Database, these are the closest matches:

{candidate_list}

Which food key best represents a typical "{food_name}" as it would appear in a meal?
Consider it is likely fresh/raw/cooked as normally eaten, not processed or a snack form.

Respond ONLY with the food key, nothing else. Example: F001234"""
            }]
        }]
    }

    response = requests.post(url, json=payload)
    if response.status_code == 200:
        result = response.json()
        key = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"DEBUG Gemini matched '{food_name}' → {key}")
        return key
    return None


def get_nutrition_by_key(food_key):
    """Get nutrition by exact food key"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT food_name, energy_kcal,
               COALESCE(protein, 0) as protein,
               COALESCE(fat, 0) as fat,
               COALESCE(carbohydrates, 0) as carbohydrates,
               COALESCE(fibre, 0) as fibre,
               COALESCE(sodium, 0) as sodium,
               COALESCE(calcium, 0) as calcium,
               COALESCE(iron, 0) as iron,
               COALESCE(magnesium, 0) as magnesium,
               COALESCE(potassium, 0) as potassium,
               COALESCE(zinc, 0) as zinc,
               COALESCE(vitamin_a, 0) as vitamin_a,
               COALESCE(vitamin_c, 0) as vitamin_c,
               COALESCE(vitamin_d, 0) as vitamin_d,
               COALESCE(vitamin_e, 0) as vitamin_e,
               COALESCE(cholesterol, 0) as cholesterol,
               COALESCE(sugars, 0) as sugars
        FROM foods_afcd
        WHERE food_key = ?
        LIMIT 1
    """, (food_key,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
