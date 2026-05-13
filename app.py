# Food Analyzer - Flask Web App
# Author: Sanyam
# Started: May 2026

import os
import json
import base64
import requests
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)

# ─── Database ────────────────────────────────────────
def get_db():
    conn = sqlite3.connect('food_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def search_food(food_name):
    """Search AFCD database with fuzzy matching"""
    conn = get_db()
    cursor = conn.cursor()

    # Try full name match first
    cursor.execute("""
        SELECT food_name, energy_kcal, protein, fat, carbohydrates
        FROM foods_afcd
        WHERE LOWER(food_name) LIKE ?
        LIMIT 1
    """, (f'%{food_name.lower()}%',))
    result = cursor.fetchone()

    # Try word by word if no match
    if not result:
        words = food_name.lower().split()
        for word in words:
            if len(word) > 3:
                cursor.execute("""
                    SELECT food_name, energy_kcal, protein, fat, carbohydrates
                    FROM foods_afcd
                    WHERE LOWER(food_name) LIKE ?
                    LIMIT 1
                """, (f'%{word}%',))
                result = cursor.fetchone()
                if result:
                    break

    conn.close()
    return dict(result) if result else None

# ─── Gemini AI ───────────────────────────────────────
def analyze_with_gemini(image_base64, mime_type="image/jpeg"):
    """Send image to Gemini for food analysis"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_base64
                    }
                },
                {
                    "text": """Analyze this food image. List each food item you see.
                    Respond ONLY in this exact JSON format, no other text:
                    {
                        "foods": [
                            {"name": "food name", "estimated_grams": 100},
                            {"name": "food name", "estimated_grams": 150}
                        ],
                        "meal_description": "brief description"
                    }"""
                }
            ]
        }]
    }

    response = requests.post(url, json=payload)
    if response.status_code == 200:
        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    else:
        return None

# ─── Routes ──────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    """Analyze food image from camera or upload"""
    try:
        data = request.get_json()
        image_base64 = data.get('image')
        mime_type = data.get('mime_type', 'image/jpeg')

        # Get AI analysis
        ai_result = analyze_with_gemini(image_base64, mime_type)
        if not ai_result:
            return jsonify({"error": "AI analysis failed"}), 500

        # Look up nutrition for each food
        foods_with_nutrition = []
        total_calories = 0

        for food in ai_result['foods']:
            nutrition = search_food(food['name'])
            grams = food['estimated_grams']

            if nutrition:
                calories = (nutrition['energy_kcal'] * grams) / 100
                protein = (nutrition['protein'] * grams) / 100
                fat = (nutrition['fat'] * grams) / 100
                carbs = (nutrition['carbohydrates'] * grams) / 100
            else:
                calories = protein = fat = carbs = 0

            foods_with_nutrition.append({
                "name": food['name'],
                "grams": grams,
                "calories": round(calories),
                "protein": round(protein, 1),
                "fat": round(fat, 1),
                "carbs": round(carbs, 1),
                "found_in_db": nutrition is not None
            })
            total_calories += calories

        result = {
            "meal_description": ai_result['meal_description'],
            "foods": foods_with_nutrition,
            "total_calories": round(total_calories),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        # Save to log
        save_meal_log(result)

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analyze-voice', methods=['POST'])
def analyze_voice():
    """Analyze food from voice text input"""
    try:
        data = request.get_json()
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

        response = requests.post(url, json=payload)
        if response.status_code == 200:
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            ai_result = json.loads(text.strip())

            # Look up nutrition
            foods_with_nutrition = []
            total_calories = 0

            for food in ai_result['foods']:
                nutrition = search_food(food['name'])
                grams = food['estimated_grams']

                if nutrition:
                    calories = (nutrition['energy_kcal'] * grams) / 100
                    protein = (nutrition['protein'] * grams) / 100
                    fat = (nutrition['fat'] * grams) / 100
                    carbs = (nutrition['carbohydrates'] * grams) / 100
                else:
                    calories = protein = fat = carbs = 0

                foods_with_nutrition.append({
                    "name": food['name'],
                    "grams": grams,
                    "calories": round(calories),
                    "protein": round(protein, 1),
                    "fat": round(fat, 1),
                    "carbs": round(carbs, 1),
                    "found_in_db": nutrition is not None
                })
                total_calories += calories

            result = {
                "meal_description": ai_result['meal_description'],
                "foods": foods_with_nutrition,
                "total_calories": round(total_calories),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
            }

            save_meal_log(result)
            return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def history():
    """Get meal history"""
    try:
        if os.path.exists('meals_log.json'):
            with open('meals_log.json', 'r') as f:
                log = json.load(f)
            return jsonify(log[-10:])  # Last 10 meals
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def save_meal_log(meal_data):
    """Save meal to JSON log"""
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