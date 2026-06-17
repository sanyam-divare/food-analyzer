# Food Analyzer - Flask Web App
# Author: Sanyam
# Version: 3.1 - Claude/Gemini Optimization + Cached Vector Matrix Search
# Started: May 2026

import os
import re
import json
import math
from io import BytesIO
from base64 import b64decode, b64encode
from datetime import datetime,timezone
from zoneinfo import ZoneInfo  # Python 3.9+
import requests
import sqlite3
from flask import Flask, render_template, request, jsonify, g
from dotenv import load_dotenv


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


# Register gut health blueprint
from gut_routes import gut_bp


TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'google_token.json')

try:
    from PIL import Image
except Exception:
    Image = None

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
AI_PROVIDER = os.getenv("AI_PROVIDER", "claude").lower()

print("DEBUG: GEMINI_API_KEY:", "YES" if GEMINI_API_KEY else "NO")
print("DEBUG: CLAUDE_API_KEY:", "YES" if CLAUDE_API_KEY else "NO")
print("DEBUG: AI_PROVIDER:", AI_PROVIDER)

# At top of file, after your imports:
GOOGLE_FIT_AVAILABLE = True  # since you import directly at top


# ══════════════════════════════════════════════════════════════════════════════
# PIN AUTH — Add these to app.py
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. Add this near the top of app.py (after imports) ────────────────────────

# PIN → patient_id mapping
# Add new patients here as Mrunal onboards them
VALID_PINS = {
    '20262026':  'guest',       # demo / doctor visit
    '20242024': 'guest',   # Sanyam first real patient
    '20252025':  'Jeet',   # second patient
    '11111111':  'testpatient',
}

def check_pin(request):
    """
    Validate PIN from request header or JSON body.
    Returns patient_id if valid, None if invalid.
    """
    pin = (
        request.headers.get('X-App-Pin') or
        (request.get_json(silent=True) or {}).get('pin') or
        request.args.get('pin') or
        ''
    ).strip().lower()
    return VALID_PINS.get(pin)


def require_pin(f):
    """
    Decorator — blocks route if PIN invalid.
    Use on any route you want to protect.
    """
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        patient_id = check_pin(request)
        if not patient_id:
            return jsonify({
                "error": "Invalid PIN",
                "code":  "AUTH_FAILED"
            }), 401
        return f(*args, **kwargs)
    return decorated



app = Flask(__name__)
# register gut app
app.register_blueprint(gut_bp)

# Global Cache to turn the slow DB loop into a lightning-fast memory scan
AFCD_EMBEDDING_CACHE = []

def load_embeddings_into_cache():
    """Load and deserialize AFCD embeddings once at startup to prevent slow DB loops, respecting FAST_MODE to save RAM."""
    global AFCD_EMBEDDING_CACHE
    
    # Check if FAST_MODE is enabled to save memory on platforms like Render
    if os.getenv("FAST_MODE", "false").lower() == "true":
        print("🚀 FAST_MODE active: Bypassing embedding cache generation to optimize memory usage.")
        AFCD_EMBEDDING_CACHE = []
        return

    try:
        conn = sqlite3.connect('food_database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT food_key, food_name, embedding FROM foods_afcd WHERE embedding IS NOT NULL")
        rows = cursor.fetchall()
        conn.close()
        
        AFCD_EMBEDDING_CACHE = []
        for row in rows:
            try:
                vec = json.loads(row['embedding'])
                AFCD_EMBEDDING_CACHE.append({
                    'food_key': row['food_key'],
                    'food_name': row['food_name'],
                    'embedding': vec
                })
            except Exception:
                continue
                
        print(f"SUCCESS: Cached {len(AFCD_EMBEDDING_CACHE)} AFCD food embeddings into memory.")
        
    except Exception as e:
        print(f"WARNING: Could not warm embedding cache: {e}")



# ── Daily nutrition targets (add near top of file) ───
DAILY_TARGETS = {
    "calories":    2000,   # kcal
    "protein":       50,   # g
    "carbs":        275,   # g
    "fat":           78,   # g
    "fibre":         30,   # g
    "sodium":      2300,   # mg
    "calcium":     1000,   # mg
    "iron":          18,   # mg
    "potassium":   3500,   # mg
    "vitamin_c":     90,   # mg
    "cholesterol":  300,   # mg
}
# ─── timezone aware function ─────────────────────────────────────────

def get_local_now():
    """Returns current time in Australian Eastern time"""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Australia/Melbourne")
        return datetime.now(tz)
    except Exception:
        # Fallback if zoneinfo not available
        return datetime.now()

# def get_local_timestamp():
#     return get_local_now().strftime("%Y-%m-%d %H:%M")

def get_local_timestamp(timezone_str=None):
    """Get current timestamp in user's local timezone"""
    try:
        if timezone_str:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(timezone_str)
            return datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        print(f"Timezone error for '{timezone_str}': {e}")
    # Fallback to server time
    return datetime.now().strftime("%Y-%m-%d %H:%M")

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

def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0

def get_query_embedding(text):
    """Get Gemini embedding for a search query"""
    if not GEMINI_API_KEY:
        return None
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={GEMINI_API_KEY}'
    try:
        r = requests.post(url, json={
            'model': 'models/gemini-embedding-2',
            'content': {'parts': [{'text': text.lower()}]}
        }, timeout=5)
        if r.status_code == 200:
            return r.json()['embedding']['values']
        request_log(f"Embedding error {r.status_code} for '{text}'")
    except Exception as e:
        request_log(f"Embedding exception: {e}")
    return None

NUTRITION_SELECT = """
SELECT food_key, food_name, energy_kcal,
COALESCE(protein, 0) as protein,
COALESCE(fat, 0) as fat,
COALESCE(carbohydrates, 0) as carbohydrates,
COALESCE(fibre, 0) as fibre,
COALESCE(sugars, 0) as sugars,
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
COALESCE(cholesterol, 0) as cholesterol
FROM foods_afcd
"""

def search_afcd_by_embedding(food_name, threshold=0.82):
    """Search cached AFCD embeddings instantly without slamming SQLite."""
    query_vec = get_query_embedding(food_name)
    if not query_vec:
        return None, 0.0

    best_score = 0.0
    best_key = None

    # Iterating over the local global cache is orders of magnitude faster
    for row in AFCD_EMBEDDING_CACHE:
        score = cosine_similarity(query_vec, row['embedding'])
        if score > best_score:
            best_score = score
            best_key = row['food_key']

    request_log(f"Vector Scan '{food_name}' → max score={best_score:.3f}")

    if best_score >= threshold:
        return best_key, best_score
    return None, best_score

def get_nutrition_by_key(food_key):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(NUTRITION_SELECT + " WHERE food_key = ? LIMIT 1", (food_key,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    except Exception as e:
        request_log(f"DB lookup failed for key {food_key}: {e}")
        return None  # falls back to AI-estimated nutrition

# ─── Prompts & Structural Verification ─────────────────
# SHARED_JSON_SCHEMA = """Respond ONLY in this exact JSON format, no other text:
# {
#   "foods": [
#     {
#       "name": "specific food name",
#       "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|not applicable",
#       "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
#       "estimated_grams": 100,
#       "confidence": "high|medium|low",
#       "nutrition_per_100g": {
#         "calories_kcal": 0, "protein_g": 0, "fat_g": 0, "carbohydrates_g": 0, "fibre_g": 0,
#         "sugar_g": 0, "sodium_mg": 0, "calcium_mg": 0, "iron_mg": 0, "magnesium_mg": 0,
#         "potassium_mg": 0, "zinc_mg": 0, "vitamin_a_ug": 0, "vitamin_c_mg": 0, "vitamin_d_ug": 0,
#         "vitamin_e_mg": 0, "cholesterol_mg": 0
#       },
#       "gut_microbiome": {
#         "prebiotic_score": 0, "probiotic_score": 0,
#         "bacteria_promoted": [], "bacteria_reduced": [],
#         "fibre_type": "soluble|insoluble|both|none",
#         "gut_health_notes": "brief clinical note"
#       }
#     }
#   ],
#   "meal_description": "brief description",
#   "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
#   "overall_gut_health_score": 0,
#   "overall_gut_notes": "overall gut health summary"
# }"""

SHARED_JSON_SCHEMA = """Analyze this food image as a clinical nutritionist.
        Identify each food item visible and estimate portion weight.
        Provide key nutrition values per 100g from your knowledge.
        For minerals/vitamins give your best estimate — approximate is fine.

        Respond ONLY in valid JSON:
        {
        "foods": [
            {
            "name": "specific food name",
            "cooking_method": "raw|grilled|fried|boiled|steamed|baked|not applicable",
            "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
            "estimated_grams": 150,
            "confidence": "high|medium|low",
            "nutrition_per_100g": {
                "calories_kcal": 95,
                "protein_g": 1.4,
                "fat_g": 0.2,
                "carbohydrates_g": 20,
                "fibre_g": 2.6,
                "sugar_g": 12,
                "sodium_mg": 1,
                "calcium_mg": 5,
                "iron_mg": 0.3,
                "potassium_mg": 358,
                "vitamin_c_mg": 8.7,
                "cholesterol_mg": 0
            }
            }
        ],
        "meal_description": "one sentence",
        "cuisine_type": "Asian|Western|Indian|Mediterranean|Mixed|Unknown",
        "overall_gut_health_score": 0,
        "overall_gut_notes": ""
        }"""

# ─── Engine Callers ───────────────────────────────────
def analyze_with_claude_vision(image_base64, mime_type="image/jpeg"):
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY in .env file"}
    request_log("Calling Claude Vision API")
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
                        {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_base64}},
                        {"type": "text", "text": f"You are a clinical nutritionist. Analyze this food image. {SHARED_JSON_SCHEMA}"}
                    ]
                }]
            }, timeout=30
        )
        if response.status_code != 200:
            return {"error": f"Claude Vision error {response.status_code}: {response.text[:200]}"}
        
        text = response.json()['content'][0]['text'].strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed Claude vision analysis: {e}"}

def analyze_with_gemini_vision(image_base64, mime_type="image/jpeg"):
    """Gemini Vision Execution equipped with structural fallback data to prevent empty values"""
    if not GEMINI_API_KEY:
        return {"error": "Missing GEMINI_API_KEY in .env file"}
    request_log("Calling Gemini Vision API")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    try:
        payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                    {"text": f"You are a clinical nutritionist. Analyze this food image. {SHARED_JSON_SCHEMA}"}
                ]
            }]
        }
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code != 200:
            return {"error": f"Gemini Vision error {response.status_code}"}
        
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"): text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed Gemini vision execution: {e}"}

def analyze_with_claude_voice(voice_text):
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
                "max_tokens": 2000,
                "messages": [{
                    "role": "user",
                    "content": f"Extract details from: '{voice_text}'. {SHARED_JSON_SCHEMA}"
                }]
            }, timeout=20
        )
        text = response.json()['content'][0]['text'].strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Claude voice parser crash: {e}"}

# def analyze_with_gemini_voice(voice_text):
#     if not GEMINI_API_KEY:
#         return {"error": "Missing GEMINI_API_KEY"}
#     url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
#     try:
#         payload = {"contents": [{"parts": [{"text": f"Extract details from: '{voice_text}'. {SHARED_JSON_SCHEMA}"}]}]}
#         r = requests.post(url, json=payload, timeout=20)
#         text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
#         if "```" in text:
#             text = text.split("```")[1]
#             if text.startswith("json"): text = text[4:]
#         return json.loads(text.strip())
#     except Exception as e:
#         return {"error": f"Gemini voice parser crash: {e}"}
def analyze_with_gemini_voice(voice_text):
    """
    Safely extracts food structures from voice inputs using robust regex extraction
    and structural verification to eliminate parsing crashes.
    """
    if not GEMINI_API_KEY:
        return {"error": "Missing GEMINI_API_KEY"}
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    try:
        payload = {
            "contents": [{
                "parts": [{"text": f"Extract details from this meal description: '{voice_text}'. {SHARED_JSON_SCHEMA}"}]
            }]
        }
        
        # Bumping timeout from 20 to 30 to allow full token generation processing windows
        r = requests.post(url, json=payload, timeout=30)
        
        if r.status_code != 200:
            return {"error": f"Gemini Voice API Error {r.status_code}: {r.text[:200]}"}
            
        response_json = r.json()
        
        # ── SAFE KEY CHECKING ─────────────────────────────────────────────────
        # Gracefully handle unexpected or empty responses from the API
        candidates = response_json.get("candidates", [])
        if not candidates or "content" not in candidates[0] or "parts" not in candidates[0]["content"]:
            return {"error": "Gemini returned an empty or flagged response payload."}
            
        raw_text = candidates[0]["content"]["parts"][0].get("text", "").strip()
        
        # ── BULLETPROOF TEXT EXTRACTION ───────────────────────────────────────
        # Use regex to safely capture anything inside a ```json ... ``` block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            clean_text = json_match.group(1).strip()
        else:
            # Fall back to using the raw text directly if no backticks are present
            clean_text = raw_text
            
        # ── SAFE JSON PARSING ─────────────────────────────────────────────────
        return json.loads(clean_text)
        
    except json.JSONDecodeError as je:
        request_log(f"JSON Parse Failure. Raw Text received: {raw_text}")
        return {"error": f"Gemini returned poorly formatted JSON: {str(je)}"}
    except Exception as e:
        return {"error": f"Gemini voice parser crash: {str(e)}"}


# ─── Nutrition Matrix Builder ─────────────────────────
def build_food_entry(food, grams, provider, afcd_data=None, afcd_score=0.0):
    n = food.get('nutrition_per_100g') or {}
    gut = food.get('gut_microbiome') or {}

    # Standardized conversion logic
    if not n and 'calories' in food:
        current_grams = food.get('grams', 100) or 100
        def to_100g(val): return (val / current_grams) * 100 if current_grams else 0
        n = {
            'calories_kcal': to_100g(food.get('calories', 0)),
            'protein_g': to_100g(food.get('protein', 0)),
            'fat_g': to_100g(food.get('fat', 0)),
            'carbohydrates_g': to_100g(food.get('carbs', 0)),
            'fibre_g': to_100g(food.get('fibre', 0)),
            'sugar_g': to_100g(food.get('sugars', 0)),
            'sodium_mg': to_100g(food.get('sodium', 0))
        }

    if afcd_data and afcd_score >= 0.82:
        source = f"AFCD verified ({afcd_score:.2f})"
        cal = afcd_data.get('energy_kcal', 0)
        prot = afcd_data.get('protein', 0)
        fat = afcd_data.get('fat', 0)
        carb = afcd_data.get('carbohydrates', 0)
        fibr = afcd_data.get('fibre', 0)
        sugr = afcd_data.get('sugars', 0)
        sod = afcd_data.get('sodium', 0)
        cal_ = afcd_data.get('calcium', 0)
        ir = afcd_data.get('iron', 0)
        mag = afcd_data.get('magnesium', 0)
        pot = afcd_data.get('potassium', 0)
        zn = afcd_data.get('zinc', 0)
        va = afcd_data.get('vitamin_a', 0)
        vc = afcd_data.get('vitamin_c', 0)
        vd = afcd_data.get('vitamin_d', 0)
        ve = afcd_data.get('vitamin_e', 0)
        chol = afcd_data.get('cholesterol', 0)
        matched_name = afcd_data.get('food_name', food.get('name', 'Unknown food'))
    else:
        source = f"{provider.capitalize()} AI estimated"
        cal = n.get('calories_kcal', 0) or 0
        prot = n.get('protein_g', 0) or 0
        fat = n.get('fat_g', 0) or 0
        carb = n.get('carbohydrates_g', 0) or 0
        fibr = n.get('fibre_g', 0) or 0
        sugr = n.get('sugar_g', 0) or 0
        sod = n.get('sodium_mg', 0) or 0
        cal_ = n.get('calcium_mg', 0) or 0
        ir = n.get('iron_mg', 0) or 0
        mag = n.get('magnesium_mg', 0) or 0
        pot = n.get('potassium_mg', 0) or 0
        zn = n.get('zinc_mg', 0) or 0
        va = n.get('vitamin_a_ug', 0) or 0
        vc = n.get('vitamin_c_mg', 0) or 0
        vd = n.get('vitamin_d_ug', 0) or 0
        ve = n.get('vitamin_e_mg', 0) or 0
        chol = n.get('cholesterol_mg', 0) or 0
        matched_name = food.get('name', 'Unknown food')

    def p(v): return round((v or 0) * grams / 100, 2)

    return {
        "name": food.get('name', 'Unknown food'),
        "matched": matched_name,
        "grams": grams,
        "confidence": food.get('confidence', 'medium'),
        "cooking_method": food.get('cooking_method', ''),
        "category": food.get('category', ''),
        "data_source": source,
        "afcd_score": round(afcd_score, 3),
        "found_in_db": afcd_data is not None and afcd_score >= 0.82,
        "calories": p(cal),
        "protein": p(prot),
        "fat": p(fat),
        "carbs": p(carb),
        "fibre": p(fibr),
        "sugars": p(sugr),
        "sodium": p(sod),
        "calcium": p(cal_),
        "iron": p(ir),
        "magnesium": p(mag),
        "potassium": p(pot),
        "zinc": p(zn),
        "vitamin_a": p(va),
        "vitamin_c": p(vc),
        "vitamin_d": p(vd),
        "vitamin_e": p(ve),
        "cholesterol": p(chol),
        "gut_microbiome": {
            "prebiotic_score": gut.get('prebiotic_score', 0) or 0,
            "probiotic_score": gut.get('probiotic_score', 0) or 0,
            "bacteria_promoted": gut.get('bacteria_promoted', []),
            "bacteria_reduced": gut.get('bacteria_reduced', []),
            "fibre_type": gut.get('fibre_type', 'none'),
            "gut_health_notes": gut.get('gut_health_notes', '')
        }
    }

# ... (Your environment variables and global variables are up here)

# ── NEW HELPER FUNCTION: PLACE THIS HERE ────────────────────────────────
import requests # Make sure requests is imported at the top of your file

def get_openai_embeddings_batch(text_list):
    """
    Fetches embeddings for ALL food items in a single API round-trip.
    Reduces 4-5 network calls down to 1.
    """
    # Grab your OpenAI key from environment variables
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY ")
    
    if not text_list or not openai_key:
        return {}
    try:
        url = "https://api.openai.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {openai_key.strip()}", "Content-Type": "application/json"}
        payload = {"input": text_list, "model": "text-embedding-3-small"}
        
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            data = res.json()["data"]
            # Map the original text back to its vector array
            return {text_list[i]: data[i]["embedding"] for i in range(len(text_list))}
        print(f"⚠️ OpenAI Batch Embedding Error: {res.status_code}")
        return {}
    except Exception as e:
        print(f"⚠️ OpenAI Batch Embedding network failure: {e}")
        return {}


# ── YOUR UPDATED CORE PIPELINE FUNCTION ─────────────────────────────────
# ─── Optimized Batch Vector Network Utilities ─────────────────────────

def get_query_embeddings_batch(text_list):
    """
    Fetches Gemini embeddings for ALL food items in a single API round-trip.
    Drastically minimizes network overhead, eliminating 503 errors and timeouts.
    """
    if not GEMINI_API_KEY or not text_list:
        return {}
        
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:batchEmbedContents?key={GEMINI_API_KEY}'
    
    try:
        # Construct the batch request format Google expects
        requests_payload = [
            {
                "model": "models/gemini-embedding-2",
                "content": {"parts": [{"text": text.lower().strip()}]}
            }
            for text in text_list
        ]
        
        request_log(f"⚡ Batch embedding {len(text_list)} items via Gemini...")
        response = requests.post(url, json={"requests": requests_payload}, timeout=10)
        
        if response.status_code == 200:
            embeddings_data = response.json().get('embeddings', [])
            # Map each input string back to its corresponding vector array
            return {text_list[i]: embeddings_data[i]['values'] for i in range(len(text_list))}
            
        request_log(f"⚠️ Batch Embedding failed with status code: {response.status_code}")
        return {}
    except Exception as e:
        request_log(f"⚠️ Batch Embedding network exception: {e}")
        return {}


def search_afcd_by_precalculated_embedding(query_vec, food_name, threshold=0.82):
    """Scans the local global memory cache instantly using a pre-calculated vector."""
    if not query_vec:
        return None, 0.0

    best_score = 0.0
    best_key = None

    # In-memory scan remains blistering fast
    for row in AFCD_EMBEDDING_CACHE:
        score = cosine_similarity(query_vec, row['embedding'])
        if score > best_score:
            best_score = score
            best_key = row['food_key']

    request_log(f"Cached Vector Scan '{food_name}' → max score={best_score:.3f}")

    if best_score >= threshold:
        return best_key, best_score
    return None, best_score


# ─── Core Pipeline Implementation ─────────────────────────────────────
import os

def calculate_nutrition(ai_result, provider):
    """
    Processes nutritional structures with an instant-pass 'FAST_MODE' option
    to skip downstream database validation loops.
    """
    foods_out = []
    total_cal = 0
    foods_list = ai_result.get('foods', [])

    # Check if Fast Mode is active (default to false if not set)
    fast_mode = os.getenv("FAST_MODE", "false").lower() == "true"

    if fast_mode:
        request_log("🚀 FAST_MODE active: Skipping embedding API calls and AFCD database lookups.")
        batch_vectors = {}
    else:
        # Gather unique food names for a single batch network call
        food_names_to_batch = list(set([str(f.get('name', '')).strip() for f in foods_list if f.get('name')]))
        batch_vectors = get_query_embeddings_batch(food_names_to_batch)

    # Core loop
    for food in foods_list:
        grams = food.get('estimated_grams', 100) or 100
        food_name = str(food.get('name', '')).strip()

        afcd_data = None
        afcd_score = 0.0

        # Run database matching ONLY if fast_mode is disabled
        if not fast_mode:
            query_vec = batch_vectors.get(food_name)
            afcd_key, afcd_score = search_afcd_by_precalculated_embedding(query_vec, food_name, threshold=0.82)
            afcd_data = get_nutrition_by_key(afcd_key) if afcd_key else None
            
            if afcd_data:
                request_log(f"AFCD verified match: {afcd_data['food_name']} (Score: {afcd_score:.2f})")

        # If fast_mode is true, build_food_entry naturally falls back 
        # to using raw provider values (Claude/Gemini) without crashing
        entry = build_food_entry(food, grams, provider, afcd_data, afcd_score)
        foods_out.append(entry)
        total_cal += entry['calories']

    return foods_out, round(total_cal, 1)

# def calculate_nutrition(ai_result, provider):
#     """
#     Optimized pipeline processing logic utilizing pre-batched Gemini embeddings 
#     to handle complex multi-ingredient analysis under 2 seconds.
#     """
#     foods_out = []
#     total_cal = 0
#     foods_list = ai_result.get('foods', [])

#     # STEP 1: Gather all unique food names for a single batch network call
#     food_names_to_batch = list(set([str(f.get('name', '')).strip() for f in foods_list if f.get('name')]))

#     # Execute exactly ONE network call to get vectors for everything on the plate
#     batch_vectors = get_query_embeddings_batch(food_names_to_batch)

#     # STEP 2: Loop through items instantly using the in-memory batch vector cache
#     for food in foods_list:
#         grams = food.get('estimated_grams', 100) or 100
#         food_name = str(food.get('name', '')).strip()

#         request_log(f"Processing '{food_name}' ({grams}g)")

#         # Extract vector from our batch payload map
#         query_vec = batch_vectors.get(food_name)
        
#         # Match using the precalculated vector against your in-memory SQLite matrix
#         afcd_key, afcd_score = search_afcd_by_precalculated_embedding(query_vec, food_name, threshold=0.82)
#         afcd_data = get_nutrition_by_key(afcd_key) if afcd_key else None

#         if afcd_data:
#             request_log(f"AFCD verified match: {afcd_data['food_name']} (Score: {afcd_score:.2f})")
#         else:
#             request_log(f"No match >= 0.82. Reverting to structural {provider} fallback parameters.")

#         entry = build_food_entry(food, grams, provider, afcd_data, afcd_score)
#         foods_out.append(entry)
#         total_cal += entry['calories']

#     return foods_out, round(total_cal, 1)


# ─── Image Resize ─────────────────────────────────────
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

# ─── Controlled API Routes ───────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_v1():
    try:
        data = request.get_json() or {}
        timezone_str = data.get('timezone', '')
        g.request_log = []
        request_log("Received /analyze request")

        image_base64 = data.get('image')
        mime_type = data.get('mime_type', 'image/jpeg')
        provider = data.get('provider', AI_PROVIDER).lower()

        request_log(f"Active Selected Provider Strategy: {provider}")
        image_base64 = resize_image(image_base64)

        if provider == 'gemini':
            ai_result = analyze_with_gemini_vision(image_base64, mime_type)
        else:
            ai_result = analyze_with_claude_vision(image_base64, mime_type)

        if isinstance(ai_result, dict) and ai_result.get('error'):
            return jsonify({"error": ai_result['error']}), 500

        foods, total_calories = calculate_nutrition(ai_result, provider)

        result = {
            "meal_description": ai_result.get('meal_description', ''),
            "cuisine_type": ai_result.get('cuisine_type', 'Unknown'),
            "overall_gut_health_score": ai_result.get('overall_gut_health_score', 0),
            "overall_gut_notes": ai_result.get('overall_gut_notes', ''),
            "foods": foods,
            "total_calories": total_calories,
            "timestamp": get_local_timestamp(timezone_str),
            "debug_log": g.request_log
        }
        # we don't want to save before confirmation    
        # save_meal_log(result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Server processing breakdown: {str(e)}"}), 500

@app.route('/confirm-meal', methods=['POST'])
def confirm_meal():
    """Save meal only when user explicitly confirms."""
    try:
        data = request.get_json() or {}
        timezone_str = data.get('timezone', '')

        meal_data = {
            "meal_description":         data.get('meal_description', ''),
            "cuisine_type":             data.get('cuisine_type', ''),
            "foods":                    data.get('foods', []),
            "total_calories":           data.get('total_calories', 0),
            "timestamp":                data.get('timestamp') or get_local_timestamp(timezone_str),
            "overall_gut_health_score": data.get('overall_gut_health_score', 0),
            "overall_gut_notes":        data.get('overall_gut_notes', ''),
        }

        save_meal_log(meal_data)
        return jsonify({"status": "saved", "timestamp": meal_data['timestamp']})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# def save_meal_log(meal_data):
#     log_file = 'meals_log.json'
#     log = []
#     if os.path.exists(log_file):
#         with open('meals_log.json', 'r') as f:
#             log = json.load(f)

#     # Fix timezone here too
#     timestamp = meal_data.get('timestamp', get_local_timestamp())
#     meal_data['meal_category'] = get_meal_category(timestamp)
#     meal_data['date'] = timestamp[:10]

#     log.append(meal_data)
#     with open(log_file, 'w') as f:
#         json.dump(log, f, indent=2)


        
@app.route('/analyze-voice', methods=['POST'])
def analyze_voice():
    try:
        data = request.get_json() or {}
        g.request_log = []
        request_log("Received /analyze-voice request")

        voice_text = data.get('text', '')
        provider = data.get('provider', AI_PROVIDER).lower()

        request_log(f"Voice Extraction Engine: {provider}")

        if provider == 'gemini':
            ai_result = analyze_with_gemini_voice(voice_text)
        else:
            ai_result = analyze_with_claude_voice(voice_text)

        if isinstance(ai_result, dict) and ai_result.get('error'):
            return jsonify({"error": ai_result['error']}), 500

        foods, total_calories = calculate_nutrition(ai_result, provider)

        result = {
            "meal_description": ai_result.get('meal_description', ''),
            "overall_gut_health_score": ai_result.get('overall_gut_health_score', 0),
            "overall_gut_notes": ai_result.get('overall_gut_notes', ''),
            "foods": foods,
            "total_calories": total_calories,
            "timestamp": get_local_timestamp(),
            "debug_log": g.request_log
        }
        # we don't want to save before confirmation - sanyam
        # save_meal_log(result)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# @app.route('/recalculate', methods=['POST'])
# def recalculate():
#     try:
#         data = request.get_json() or {}
#         foods = data.get('foods', [])
#         provider = data.get('provider', AI_PROVIDER).lower()

#         recalculated = []
#         for item in foods:
#             name = str(item.get('name', '') or '').strip()
#             try:
#                 grams = float(item.get('grams', 0) or 0)
#             except Exception:
#                 grams = 100

#             afcd_key, afcd_score = search_afcd_by_embedding(name, threshold=0.82)
#             afcd_data = get_nutrition_by_key(afcd_key) if afcd_key else None

#             fake_food = {
#                 "name": name,
#                 "confidence": item.get('confidence', 'medium'),
#                 "cooking_method": item.get('cooking_method', ''),
#                 "category": item.get('category', ''),
#                 "nutrition_per_100g": None,
#                 "gut_microbiome": item.get('gut_microbiome', {})
#             }
#             entry = build_food_entry(fake_food, grams, provider, afcd_data, afcd_score)
#             recalculated.append(entry)

#         return jsonify({'foods': recalculated})
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

@app.route('/recalculate', methods=['POST'])
def recalculate():
    try:
        data = request.get_json() or {}
        foods = data.get('foods', [])
        if not isinstance(foods, list):
            return jsonify({'error': 'Invalid payload'}), 400

        recalculated = []

        for item in foods:
            name = str(item.get('name', '') or '').strip()
            try:
                grams = float(item.get('grams', 0) or 0)
            except Exception:
                grams = 100

            afcd_data = None
            afcd_score = 0.0

            if name:
                fast_mode = os.getenv("FAST_MODE", "false").lower() == "true"

                if not fast_mode and AFCD_EMBEDDING_CACHE:
                    # ── Use your existing vector cache ──
                    afcd_key, afcd_score = search_afcd_by_embedding(
                        name, threshold=0.75  # slightly lower for manual entry
                    )
                    afcd_data = get_nutrition_by_key(afcd_key) if afcd_key else None

                # ── Fallback: direct SQLite fuzzy search ──
                if not afcd_data:
                    afcd_data = fuzzy_search_sqlite(name)
                    if afcd_data:
                        afcd_score = 0.70  # reasonable confidence for fuzzy match

            # Build fake food structure matching what build_food_entry expects
            fake_food = {
                "name": name,
                "confidence": item.get('confidence', 'medium'),
                "cooking_method": item.get('cooking_method', ''),
                "category": item.get('category', ''),
                "nutrition_per_100g": None,
                "gut_microbiome": item.get('gut_microbiome', {})
            }

            entry = build_food_entry(
                fake_food, grams, AI_PROVIDER, afcd_data, afcd_score
            )

            # Add per100 for JS calculateRowNutrition compatibility
            if afcd_data:
                entry['per100'] = {
                    'energy_kcal':   afcd_data.get('energy_kcal', 0),
                    'protein':       afcd_data.get('protein', 0),
                    'fat':           afcd_data.get('fat', 0),
                    'carbohydrates': afcd_data.get('carbohydrates', 0),
                    'fibre':         afcd_data.get('fibre', 0),
                    'sugars':        afcd_data.get('sugars', 0),
                    'sodium':        afcd_data.get('sodium', 0),
                    'calcium':       afcd_data.get('calcium', 0),
                    'iron':          afcd_data.get('iron', 0),
                    'magnesium':     afcd_data.get('magnesium', 0),
                    'potassium':     afcd_data.get('potassium', 0),
                    'zinc':          afcd_data.get('zinc', 0),
                    'vitamin_a':     afcd_data.get('vitamin_a', 0),
                    'vitamin_c':     afcd_data.get('vitamin_c', 0),
                    'vitamin_d':     afcd_data.get('vitamin_d', 0),
                    'vitamin_e':     afcd_data.get('vitamin_e', 0),
                    'cholesterol':   afcd_data.get('cholesterol', 0),
                }

            recalculated.append(entry)

        return jsonify({'foods': recalculated})

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def fuzzy_search_sqlite(food_name):
    """
    Direct SQLite fuzzy search — fallback when embedding cache misses.
    Handles plurals, partial matches, and word-by-word search.
    No external API calls needed.
    """
    conn = get_db()
    cursor = conn.cursor()
    normalized = food_name.lower().strip()

    # Build words list — also try stemmed versions (eggs→egg)
    raw_words = normalized.split()
    stemmed_words = []
    for w in raw_words:
        stemmed_words.append(w)
        if w.endswith('es') and len(w) > 4:
            stemmed_words.append(w[:-2])   # tomatoes → tomat
        elif w.endswith('s') and len(w) > 3:
            stemmed_words.append(w[:-1])   # eggs → egg ✅

    # Remove duplicates while preserving order
    seen = set()
    all_words = []
    for w in stemmed_words:
        if w not in seen and len(w) > 2:
            seen.add(w)
            all_words.append(w)

    result = None

    # Step 1 — exact phrase match
    cursor.execute(
        NUTRITION_SELECT + " WHERE LOWER(food_name) LIKE ? ORDER BY LENGTH(food_name) ASC LIMIT 1",
        (f'%{normalized}%',)
    )
    result = cursor.fetchone()

    # Step 2 — all words present
    if not result and len(all_words) > 1:
        clause = ' AND '.join(['LOWER(food_name) LIKE ?'] * len(all_words))
        params = [f'%{w}%' for w in all_words]
        cursor.execute(
            NUTRITION_SELECT + f" WHERE {clause} ORDER BY LENGTH(food_name) ASC LIMIT 1",
            params
        )
        result = cursor.fetchone()

    # Step 3 — any single word match (including stemmed)
    if not result:
        for word in all_words:
            cursor.execute(
                NUTRITION_SELECT + " WHERE LOWER(food_name) LIKE ? ORDER BY LENGTH(food_name) ASC LIMIT 1",
                (f'%{word}%',)
            )
            result = cursor.fetchone()
            if result:
                break

    conn.close()
    return dict(result) if result else None

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

# def save_meal_log(meal_data):
#     log_file = 'meals_log.json'
#     log = []
#     try:
#         if os.path.exists(log_file):
#             with open(log_file, 'r') as f:
#                 log = json.load(f)
#         log.append(meal_data)
#         with open(log_file, 'w') as f:
#             json.dump(log, f, indent=2)
#     except Exception as e:
#         print(f"Failed to save meal log: {e}")

# ─── ADD THESE TO app.py ─────────────────────────────
# 
# 1. Replace save_meal_log with this version
# 2. Add the new routes below
# 3. Add DAILY_TARGETS constant near top of file

# @app.before_request
# def global_pin_check():
#     open_paths     = ['/static/', '/auth/', '/debug/', '/clear-cache']
#     open_endpoints = ['index', 'static', 'debug_pin', 'clear_cache']

#     if request.endpoint in open_endpoints:
#         return None
#     if any(request.path.startswith(p) for p in open_paths):
#         return None

# @app.route('/debug/pin')
# def debug_pin():
#     return '''
#     <script>
#     var pin = localStorage.getItem('food_analyzer_pin');
#     document.write('<h2>Stored PIN: ' + pin + '</h2>');
#     document.write('<h2>Length: ' + (pin ? pin.length : 0) + '</h2>');
#     document.write('<br><button onclick="localStorage.clear();location.reload()">Clear & Reload</button>');
#     </script>
#     '''

# # Add to app.py temporarily
# @app.route('/clear-cache')
# def clear_cache():
#     return '''
#     <script>
#     localStorage.clear();
#     sessionStorage.clear();
#     alert("Cache cleared! Redirecting...");
#     window.location.href = "/";
#     </script>
#     '''
# ── Meal time categorization ──────────────────────────
def get_meal_category(timestamp_str):
    """
    Auto-assign meal category based on time of day
    Breakfast:  05:00 - 10:59
    Morning Snack: 11:00 - 11:59
    Lunch:      12:00 - 14:59
    Afternoon Snack: 15:00 - 17:59
    Dinner:     18:00 - 21:59
    Late Snack: 22:00 - 04:59
    """
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
        hour = dt.hour
        if   5  <= hour <= 10: return "Breakfast"
        elif 11 <= hour <= 11: return "Morning Snack"
        elif 12 <= hour <= 14: return "Lunch"
        elif 15 <= hour <= 17: return "Afternoon Snack"
        elif 18 <= hour <= 21: return "Dinner"
        else:                  return "Late Snack"
    except Exception:
        return "Meal"

# ── Replace existing save_meal_log with this ─────────
def save_meal_log(meal_data):
    log_file = 'meals_log.json'
    log = []
    if os.path.exists(log_file):
        with open('meals_log.json', 'r') as f:
            log = json.load(f)

    # Auto-assign meal category based on time
    timestamp = meal_data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M"))
    meal_data['meal_category'] = get_meal_category(timestamp)
    meal_data['date'] = timestamp[:10]  # YYYY-MM-DD

    log.append(meal_data)
    with open(log_file, 'w') as f:
        json.dump(log, f, indent=2)

# ── Add these new routes to app.py ───────────────────

@app.route('/history/daily', methods=['GET'])
def history_daily():
    """
    Return today's meals grouped by meal category with nutrition gaps.
    Query param: ?date=YYYY-MM-DD (defaults to today)
    """
    try:
        target_date = request.args.get('date', get_local_now().strftime("%Y-%m-%d"))

        if not os.path.exists('meals_log.json'):
            return jsonify(build_empty_daily(target_date))

        with open('meals_log.json', 'r') as f:
            log = json.load(f)

        # Filter to target date
        day_meals = [m for m in log if m.get('date') == target_date or
                     (m.get('timestamp', '').startswith(target_date))]

        # Backfill category for old entries without it
        for m in day_meals:
            if 'meal_category' not in m:
                m['meal_category'] = get_meal_category(m.get('timestamp', ''))
            if 'date' not in m:
                m['date'] = m.get('timestamp', '')[:10]

        # Group by category in timeline order
        timeline_order = [
            "Breakfast",
            "Morning Snack",
            "Lunch",
            "Afternoon Snack",
            "Dinner",
            "Late Snack"
        ]

        grouped = {cat: [] for cat in timeline_order}
        for meal in day_meals:
            cat = meal.get('meal_category', 'Meal')
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(meal)

        # Calculate totals per category and overall
        daily_totals = {k: 0.0 for k in DAILY_TARGETS}
        timeline = []

        for cat in timeline_order:
            meals = grouped[cat]
            if not meals:
                continue

            cat_totals = {k: 0.0 for k in DAILY_TARGETS}
            for meal in meals:
                for food in meal.get('foods', []):
                    cat_totals['calories']    += food.get('calories', 0) or 0
                    cat_totals['protein']     += food.get('protein', 0) or 0
                    cat_totals['carbs']       += food.get('carbs', food.get('carbohydrates', 0)) or 0
                    cat_totals['fat']         += food.get('fat', 0) or 0
                    cat_totals['fibre']       += food.get('fibre', 0) or 0
                    cat_totals['sodium']      += food.get('sodium', 0) or 0
                    cat_totals['calcium']     += food.get('calcium', 0) or 0
                    cat_totals['iron']        += food.get('iron', 0) or 0
                    cat_totals['potassium']   += food.get('potassium', 0) or 0
                    cat_totals['vitamin_c']   += food.get('vitamin_c', 0) or 0
                    cat_totals['cholesterol'] += food.get('cholesterol', 0) or 0

            for k in daily_totals:
                daily_totals[k] += cat_totals[k]

            timeline.append({
                "category":   cat,
                "meals":      meals,
                "totals":     {k: round(v, 1) for k, v in cat_totals.items()},
                "meal_count": len(meals)
            })

        # Calculate nutrition gaps
        gaps = calculate_nutrition_gaps(daily_totals)

        return jsonify({
            "date":          target_date,
            "timeline":      timeline,
            "daily_totals":  {k: round(v, 1) for k, v in daily_totals.items()},
            "daily_targets": DAILY_TARGETS,
            "gaps":          gaps,
            "meal_count":    len(day_meals)
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


def calculate_nutrition_gaps(totals):
    """
    Calculate deficiencies and generate actionable alerts.
    Returns list of gap alerts sorted by severity.
    """
    alerts = []

    checks = [
        {
            "key":      "calories",
            "label":    "Calories",
            "unit":     "kcal",
            "target":   DAILY_TARGETS["calories"],
            "low_msg":  "You're under your calorie goal. Consider a nutritious snack.",
            "high_msg": "You've exceeded your daily calorie target.",
            "low_pct":  0.75,   # alert if below 75% of target
            "high_pct": 1.10,   # alert if above 110% of target
        },
        {
            "key":      "protein",
            "label":    "Protein",
            "unit":     "g",
            "target":   DAILY_TARGETS["protein"],
            "low_msg":  "Protein intake is low. Add chicken, fish, eggs, legumes or dairy.",
            "high_msg": "Protein intake is above target — check if intentional.",
            "low_pct":  0.70,
            "high_pct": 2.00,
        },
        {
            "key":      "fibre",
            "label":    "Fibre",
            "unit":     "g",
            "target":   DAILY_TARGETS["fibre"],
            "low_msg":  "Low fibre today. Add vegetables, wholegrains, legumes or fruit.",
            "high_msg": None,
            "low_pct":  0.60,
            "high_pct": 99,
        },
        {
            "key":      "calcium",
            "label":    "Calcium",
            "unit":     "mg",
            "target":   DAILY_TARGETS["calcium"],
            "low_msg":  "Calcium is low. Include dairy, leafy greens or fortified foods.",
            "high_msg": None,
            "low_pct":  0.50,
            "high_pct": 99,
        },
        {
            "key":      "iron",
            "label":    "Iron",
            "unit":     "mg",
            "target":   DAILY_TARGETS["iron"],
            "low_msg":  "Iron intake is low. Include red meat, legumes, spinach or fortified cereals.",
            "high_msg": None,
            "low_pct":  0.50,
            "high_pct": 99,
        },
        {
            "key":      "vitamin_c",
            "label":    "Vitamin C",
            "unit":     "mg",
            "target":   DAILY_TARGETS["vitamin_c"],
            "low_msg":  "Vitamin C is low. Add citrus fruit, capsicum, broccoli or kiwi.",
            "high_msg": None,
            "low_pct":  0.50,
            "high_pct": 99,
        },
        {
            "key":      "sodium",
            "label":    "Sodium",
            "unit":     "mg",
            "target":   DAILY_TARGETS["sodium"],
            "low_msg":  None,
            "high_msg": "Sodium is high. Reduce processed foods, sauces and added salt.",
            "low_pct":  0,
            "high_pct": 1.00,
        },
        {
            "key":      "cholesterol",
            "label":    "Cholesterol",
            "unit":     "mg",
            "target":   DAILY_TARGETS["cholesterol"],
            "low_msg":  None,
            "high_msg": "Cholesterol is above recommended limit. Limit egg yolks, organ meats and saturated fats.",
            "low_pct":  0,
            "high_pct": 1.00,
        },
    ]

    for c in checks:
        consumed = totals.get(c["key"], 0) or 0
        target   = c["target"]
        pct      = consumed / target if target else 0
        gap      = target - consumed  # positive = deficit, negative = excess

        if consumed == 0:
            # No data recorded — only flag if past breakfast time
            hour = datetime.now().hour
            if hour >= 12 and c["key"] in ("calories", "protein", "fibre"):
                alerts.append({
                    "key":      c["key"],
                    "label":    c["label"],
                    "severity": "warning",
                    "consumed": 0,
                    "target":   target,
                    "gap":      target,
                    "unit":     c["unit"],
                    "pct":      0,
                    "message":  f"No {c['label'].lower()} recorded yet today.",
                    "type":     "missing"
                })
            continue

        if pct < c["low_pct"] and c["low_msg"]:
            severity = "high" if pct < c["low_pct"] * 0.6 else "medium"
            alerts.append({
                "key":      c["key"],
                "label":    c["label"],
                "severity": severity,
                "consumed": round(consumed, 1),
                "target":   target,
                "gap":      round(gap, 1),
                "unit":     c["unit"],
                "pct":      round(pct * 100, 0),
                "message":  c["low_msg"],
                "type":     "deficient"
            })

        elif pct > c["high_pct"] and c["high_msg"]:
            alerts.append({
                "key":      c["key"],
                "label":    c["label"],
                "severity": "caution",
                "consumed": round(consumed, 1),
                "target":   target,
                "gap":      round(gap, 1),
                "unit":     c["unit"],
                "pct":      round(pct * 100, 0),
                "message":  c["high_msg"],
                "type":     "excess"
            })
        else:
            # On track
            alerts.append({
                "key":      c["key"],
                "label":    c["label"],
                "severity": "good",
                "consumed": round(consumed, 1),
                "target":   target,
                "gap":      round(gap, 1),
                "unit":     c["unit"],
                "pct":      round(pct * 100, 0),
                "message":  f"{c['label']} is on track.",
                "type":     "ok"
            })

    # Sort: high severity first, then medium, then caution, then good
    order = {"high": 0, "medium": 1, "warning": 2, "caution": 3, "good": 4}
    alerts.sort(key=lambda a: order.get(a["severity"], 5))

    return alerts


def build_empty_daily(target_date):
    return {
        "date":          target_date,
        "timeline":      [],
        "daily_totals":  {k: 0 for k in DAILY_TARGETS},
        "daily_targets": DAILY_TARGETS,
        "gaps":          [],
        "meal_count":    0
    }


#####################################################################################

# Add this global list near the top of your Flask file to hold records temporarily
stored_health_data = []

@app.route('/api/health-sync', methods=['POST'])
def receive_health_data():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    data = request.get_json()
    print(data)
    
    # Save the incoming record to our memory storage
    stored_health_data.append(data)
    
    # Keep only the last 20 entries so memory doesn't bloat
    if len(stored_health_data) > 20:
        stored_health_data.pop(0)
        
    return jsonify({"status": "success", "message": "Data saved"}), 200

# NEW ROUTE: Fetch the data from your terminal
@app.route('/api/get-health', methods=['GET'])
def get_health_data():
    return jsonify(stored_health_data), 200
#####################################################################################

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GOOGLE_FIT_AVAILABLE = True
except ImportError:
    GOOGLE_FIT_AVAILABLE = False
    print("WARNING: Google Fit libraries not installed. Run: pip install google-auth google-api-python-client")

SCOPES = ['https://www.googleapis.com/auth/fitness.activity.read']


def get_fitness_data_retire():
    if not GOOGLE_FIT_AVAILABLE:
        return {"available": False, "error": "Google Fit libraries not installed"}

    try:
        creds, error = get_google_credentials()
        if error:
            return {"available": False, "error": error}

        # Setup the Google Fit API service
        service  = build('fitness', 'v1', credentials=creds)
        now      = datetime.now(timezone.utc)
        start    = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ms = int(start.timestamp() * 1000)
        end_ms   = int(now.timestamp() * 1000)

        # FIXED: Requesting only the working Steps and Active Calorie streams
        response = service.users().dataset().aggregate(
            userId='me',
            body={
                "aggregateBy": [
                    {"dataTypeName": "com.google.step_count.delta"},
                    {"dataTypeName": "com.google.calories.expended"}
                ],
                "bucketByTime": {"durationMillis": max(1, end_ms - start_ms)},
                "startTimeMillis": start_ms,
                "endTimeMillis":   end_ms
            }
        ).execute()

        steps     = 0
        total_cal = 0.0

        buckets = response.get('bucket', [])
        if buckets:
            datasets = buckets[0].get('dataset', [])
            
            # Extract steps safely
            if len(datasets) > 0:
                pts = datasets[0].get('point', [])
                if pts:
                    steps = pts[-1]['value'][0].get('intVal', 0)
                    
            # Extract active calories expended safely
            if len(datasets) > 1:
                pts = datasets[1].get('point', [])
                if pts:
                    total_cal = pts[-1]['value'][0].get('fpVal', 0.0)

        # Programmatic BMR fallback (Calculates ~1700 kcal baseline split across the day)
        current_hour = max(1, now.hour)
        estimated_bmr_so_far = round((1700 / 24) * current_hour, 1)

        active_cal = round(total_cal, 1)
        display_total_cal = round(estimated_bmr_so_far + active_cal, 1)

        print(f"Fitness Sync: steps={steps}, active_burn={active_cal}, est_bmr={estimated_bmr_so_far}")

        # Assuming you have a helper function to categorize activity levels
        activity = classify_activity(steps, active_cal, now.hour)

        return {
            "available":       True,
            "steps":           steps,
            "calories_total":  display_total_cal, 
            "calories_bmr":    estimated_bmr_so_far,
            "calories_burned": active_cal,          
            "activity_level":  activity["level"],
            "activity_label":  activity["label"],
            "activity_emoji":  activity["emoji"],
            "timestamp":       now.strftime("%H:%M"),
        }

    except Exception as e:
        print(f"Fitness pipeline failure: {e}")
        return {"available": False, "error": str(e)}



def classify_activity_retire(steps, cal_burn, hour):
    """Classify activity level based on steps and calories burned so far today"""
    # Extrapolate to full day if it's not end of day
    if hour < 20:
        projected_steps = int(steps * (24 / max(hour, 1)))
    else:
        projected_steps = steps

    if projected_steps >= 15000 or cal_burn >= 600:
        return {"level": "intense",   "label": "Very Active Day",  "emoji": "🔥"}
    elif projected_steps >= 10000 or cal_burn >= 400:
        return {"level": "active",    "label": "Active Day",       "emoji": "⚡"}
    elif projected_steps >= 6000 or cal_burn >= 250:
        return {"level": "moderate",  "label": "Moderate Activity","emoji": "🚶"}
    elif projected_steps >= 3000 or cal_burn >= 100:
        return {"level": "light",     "label": "Light Activity",   "emoji": "😊"}
    else:
        return {"level": "sedentary", "label": "Sedentary Day",    "emoji": "💺"}


def get_fitness_data():
    if not GOOGLE_FIT_AVAILABLE:
        return {"available": False, "error": "Google Fit libraries not installed"}

    try:
        creds, error = get_google_credentials()
        if error:
            return {"available": False, "error": error}

        # Setup the Google Fit API service
        service  = build('fitness', 'v1', credentials=creds)
        now      = datetime.now(timezone.utc)
        start    = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_ms = int(start.timestamp() * 1000)
        end_ms   = int(now.timestamp() * 1000)

        # Requesting Steps and Total Expended Calories (which includes native BMR)
        response = service.users().dataset().aggregate(
            userId='me',
            body={
                "aggregateBy": [
                    {"dataTypeName": "com.google.step_count.delta"},
                    {"dataTypeName": "com.google.calories.expended"}
                ],
                "bucketByTime": {"durationMillis": max(1, end_ms - start_ms)},
                "startTimeMillis": start_ms,
                "endTimeMillis":   end_ms
            }
        ).execute()

        steps     = 0
        total_cal = 0.0

        buckets = response.get('bucket', [])
        if buckets:
            datasets = buckets[0].get('dataset', [])
            
            # Extract steps safely
            if len(datasets) > 0:
                pts = datasets[0].get('point', [])
                if pts:
                    steps = pts[-1]['value'][0].get('intVal', 0)
                    
            # Extract total calories expended safely
            if len(datasets) > 1:
                pts = datasets[1].get('point', [])
                if pts:
                    total_cal = pts[-1]['value'][0].get('fpVal', 0.0)

        # ── MATHEMATICAL CORRECTION BLOCK ───────────────────────────────
        # 1. Calculate background resting BMR split across the day (assuming 1700 baseline)
        current_hour = max(1, now.hour)
        estimated_bmr_so_far = round((1700 / 24) * current_hour, 1)

        google_raw_total = round(total_cal, 1)

        # 2. Prevent conversion distortion from Android background cloud sync lag
        if google_raw_total > estimated_bmr_so_far:
            # Server is completely synced up. Extract true active movement burn.
            active_cal = round(google_raw_total - estimated_bmr_so_far, 1)
            display_total_cal = google_raw_total
        else:
            # Server is lagging/empty. Derive realistic active calorie burn from step count.
            # Standard physiological baseline: ~0.04 kcal burned per step
            active_cal = round(steps * 0.04, 1)
            display_total_cal = round(estimated_bmr_so_far + active_cal, 1)

        print(f"Fitness Sync Cleaned: steps={steps}, active_burn={active_cal}, est_bmr={estimated_bmr_so_far}")

        # Classify using the newly corrected active calorie metric
        activity = classify_activity(steps, active_cal, now.hour)

        return {
            "available":       True,
            "steps":           steps,
            "calories_total":  display_total_cal, 
            "calories_bmr":    estimated_bmr_so_far,
            "calories_burned": active_cal,          
            "activity_level":  activity["level"],
            "activity_label":  activity["label"],
            "activity_emoji":  activity["emoji"],
            "timestamp":       now.strftime("%H:%M"),
        }

    except Exception as e:
        print(f"Fitness pipeline failure: {e}")
        return {"available": False, "error": str(e)}


def classify_activity(steps, cal_burn, hour):
    """Classify activity level based on steps and active calories burned so far today"""
    # Extrapolate to full day if checked early to prevent false 'sedentary' classifications
    if hour < 20:
        projected_steps = int(steps * (24 / max(hour, 1)))
    else:
        projected_steps = steps

    # FIXED: Scale boundaries down to isolate active movement metrics explicitly
    if projected_steps >= 12000 or cal_burn >= 500:
        return {"level": "intense", "label": "Very Active Day", "emoji": "🔥"}
    elif projected_steps >= 8000 or cal_burn >= 300:
        return {"level": "active", "label": "Active Day", "emoji": "⚡"}
    elif projected_steps >= 5000 or cal_burn >= 150:
        return {"level": "moderate", "label": "Moderate Activity", "emoji": "🚶"}
    elif projected_steps >= 2000 or cal_burn >= 50:
        return {"level": "light", "label": "Light Activity", "emoji": "😊"}
    else:
        return {"level": "sedentary", "label": "Sedentary Day", "emoji": "💺"}
        

# # ── Smart nutrition recommendations ──────────────────
# def get_smart_recommendations(fitness_data, daily_totals, daily_targets, timeline):
#     """
#     Generate personalized recommendations based on:
#     - Calories burned (Google Fit)
#     - Calories consumed so far
#     - Activity level
#     - Time of day
#     - Nutrition gaps
#     """
#     if not fitness_data.get("available"):
#         return get_basic_recommendations(daily_totals, daily_targets, timeline)

#     steps        = fitness_data.get("steps", 0)
#     cal_burn     = fitness_data.get("calories_burned", 0)
#     level        = fitness_data.get("activity_level", "sedentary")
#     hour         = datetime.now().hour
#     cal_consumed = daily_totals.get("calories", 0)

#     # Base metabolic rate (BMR) estimate ~1600-2000 kcal
#     # Total daily energy = BMR + activity calories
#     base_target  = daily_targets.get("calories", 2000)
#     total_target = base_target + cal_burn  # adjust target upward by calories burned
#     cal_gap      = total_target - cal_consumed
#     cal_gap      = round(cal_gap, 0)

#     recs = []

#     # ── Activity-based recommendations ───────────────
#     if level == "intense":
#         recs.append({
#             "type":    "activity",
#             "emoji":   "🔥",
#             "title":   "Intense Day Detected!",
#             "message": f"You've burned {cal_burn:.0f} extra calories today ({steps:,} steps). "
#                        f"Your adjusted calorie target is {total_target:.0f} kcal. "
#                        f"You still need {cal_gap:.0f} kcal — focus on protein-rich foods for recovery.",
#             "actions": [
#                 "🥩 Grilled chicken or fish (high protein recovery)",
#                 "🥑 Add healthy fats — avocado, nuts or olive oil",
#                 "🍚 Complex carbs — brown rice or sweet potato to replenish glycogen",
#                 "💧 Rehydrate — aim for 2-3 more glasses of water"
#             ],
#             "priority": "high"
#         })
#     elif level == "active":
#         recs.append({
#             "type":    "activity",
#             "emoji":   "⚡",
#             "title":   "Active Day — Well Done!",
#             "message": f"You've burned {cal_burn:.0f} calories ({steps:,} steps). "
#                        f"Adjusted target: {total_target:.0f} kcal. "
#                        f"Remaining: {cal_gap:.0f} kcal.",
#             "actions": [
#                 "🥗 Balanced dinner with protein, veg and wholegrains",
#                 "🍌 A piece of fruit makes a great post-activity snack",
#                 "💧 Keep hydrating"
#             ],
#             "priority": "medium"
#         })
#     elif level == "moderate":
#         recs.append({
#             "type":    "activity",
#             "emoji":   "🚶",
#             "title":   "Moderate Activity Today",
#             "message": f"{steps:,} steps · {cal_burn:.0f} kcal burned. "
#                        f"Remaining calories today: {cal_gap:.0f} kcal.",
#             "actions": [
#                 "🥦 Fill half your plate with vegetables at dinner",
#                 "🍗 Lean protein portion the size of your palm"
#             ],
#             "priority": "low"
#         })
#     elif level == "sedentary":
#         recs.append({
#             "type":    "activity",
#             "emoji":   "💺",
#             "title":   "Low Activity Today",
#             "message": f"Only {steps:,} steps so far. "
#                        f"Consider a 20-minute walk after dinner — burns ~100 kcal and aids digestion.",
#             "actions": [
#                 "🚶 Take a 20-min walk after your next meal",
#                 "🥗 Light dinner — salad with lean protein",
#                 "❌ Avoid heavy carbs late in the evening"
#             ],
#             "priority": "medium"
#         })

#     # ── Time-based meal recommendations ──────────────
#     if hour >= 16 and hour <= 19:
#         # Pre-dinner window
#         if cal_gap > 600:
#             recs.append({
#                 "type":    "meal_timing",
#                 "emoji":   "🍽️",
#                 "title":   "Dinner Recommendation",
#                 "message": f"You have {cal_gap:.0f} kcal remaining. Based on your activity, "
#                            f"here are 3 dinner options to optimize recovery:",
#                 "actions": [
#                     f"🥩 Option 1: Grilled salmon (150g) + roasted vegetables + brown rice (~550 kcal, 35g protein)",
#                     f"🍗 Option 2: Chicken stir-fry with broccoli and noodles (~480 kcal, 40g protein)",
#                     f"🌱 Option 3: Lentil curry with spinach and wholegrain bread (~420 kcal, 22g protein)"
#                 ],
#                 "priority": "high"
#             })
#         elif cal_gap < 200:
#             recs.append({
#                 "type":    "meal_timing",
#                 "emoji":   "⚠️",
#                 "title":   "Light Dinner Advised",
#                 "message": f"You've consumed {cal_consumed:.0f} kcal and only have {cal_gap:.0f} kcal remaining. "
#                            f"Keep dinner light tonight.",
#                 "actions": [
#                     "🥗 Large salad with grilled protein",
#                     "🍲 Clear soup with vegetables",
#                     "🚫 Skip the bread and dessert tonight"
#                 ],
#                 "priority": "medium"
#             })

#     elif hour >= 10 and hour <= 13:
#         # Pre-lunch window
#         if steps < 3000:
#             recs.append({
#                 "type":    "meal_timing",
#                 "emoji":   "☀️",
#                 "title":   "Lunch Suggestion",
#                 "message": "Low morning activity. A light but protein-rich lunch will keep energy stable.",
#                 "actions": [
#                     "🥙 Wrap with lean protein and salad",
#                     "🍜 Soup with lentils or chickpeas",
#                     "☕ Avoid heavy carb-only meals — they'll cause afternoon energy crash"
#                 ],
#                 "priority": "low"
#             })

#     # ── Nutrient gap recommendations ─────────────────
#     protein_consumed = daily_totals.get("protein", 0)
#     protein_target   = daily_targets.get("protein", 50)
#     if protein_consumed < protein_target * 0.6 and hour >= 14:
#         recs.append({
#             "type":    "nutrient",
#             "emoji":   "💪",
#             "title":   "Protein Deficit",
#             "message": f"Only {protein_consumed:.0f}g protein so far (target: {protein_target}g). "
#                        f"Especially important on an active day for muscle recovery.",
#             "actions": [
#                 "🥚 Add eggs, Greek yogurt or cottage cheese",
#                 "🐟 Fish or chicken at your next meal",
#                 "🥜 Handful of nuts or a protein-rich snack now"
#             ],
#             "priority": "high" if level in ("intense", "active") else "medium"
#         })

#     fibre_consumed = daily_totals.get("fibre", 0)
#     if fibre_consumed < 15 and hour >= 16:
#         recs.append({
#             "type":    "nutrient",
#             "emoji":   "🌿",
#             "title":   "Low Fibre Today",
#             "message": f"Only {fibre_consumed:.0f}g fibre (target: 30g). "
#                        f"Low fibre affects gut health and satiety.",
#             "actions": [
#                 "🥦 Load up on vegetables at dinner",
#                 "🍎 Eat a piece of fruit with skin",
#                 "🌾 Choose wholegrain bread or brown rice"
#             ],
#             "priority": "medium"
#         })

#     # Sort by priority
#     order = {"high": 0, "medium": 1, "low": 2}
#     recs.sort(key=lambda r: order.get(r.get("priority", "low"), 2))

#     return {
#         "available":      True,
#         "cal_burned":     cal_burn,
#         "cal_consumed":   round(cal_consumed, 0),
#         "cal_target_adj": round(total_target, 0),
#         "cal_remaining":  round(cal_gap, 0),
#         "steps":          steps,
#         "activity_level": level,
#         "activity_label": fitness_data.get("activity_label", ""),
#         "activity_emoji": fitness_data.get("activity_emoji", ""),
#         "recommendations": recs
#     }


# def get_basic_recommendations(daily_totals, daily_targets, timeline):
#     """Fallback recommendations when Google Fit is not available"""
#     cal_consumed = daily_totals.get("calories", 0)
#     cal_target   = daily_targets.get("calories", 2000)
#     cal_gap      = cal_target - cal_consumed
#     hour         = datetime.now().hour
#     recs         = []

#     if cal_consumed == 0 and hour >= 12:
#         recs.append({
#             "type":    "reminder",
#             "emoji":   "📝",
#             "title":   "No meals logged today",
#             "message": "Start logging your meals to get personalized recommendations.",
#             "actions": ["📸 Take a photo of your next meal to begin tracking"],
#             "priority": "high"
#         })
#     elif cal_gap > 500:
#         recs.append({
#             "type":    "calorie",
#             "emoji":   "🍽️",
#             "title":   f"{cal_gap:.0f} kcal remaining today",
#             "message": "You still have room for a balanced meal.",
#             "actions": [
#                 "🥗 Balanced meal with protein, veg and complex carbs",
#                 "🍎 Healthy snack if it's not meal time yet"
#             ],
#             "priority": "medium"
#         })
#     elif cal_gap < 0:
#         recs.append({
#             "type":    "calorie",
#             "emoji":   "⚠️",
#             "title":   f"Over daily target by {abs(cal_gap):.0f} kcal",
#             "message": "Consider a light activity after dinner.",
#             "actions": [
#                 "🚶 20-minute walk after dinner",
#                 "🚫 Skip dessert or late-night snacks"
#             ],
#             "priority": "medium"
#         })

#     return {
#         "available":       False,
#         "cal_consumed":    round(cal_consumed, 0),
#         "cal_target_adj":  cal_target,
#         "cal_remaining":   round(cal_gap, 0),
#         "recommendations": recs
#     }
# ─── Recommendation Copy Library ──────────────────────────────────────────────

TIME_SLOT_RECS = {
    "early_morning": {  # 05:00–08:59
        "emoji": "🌅",
        "title": "Morning Activation Window",
        "message": "Your cortisol is peaking right now — the body's natural alarm system. Use it. This is the highest-leverage window for nutrient absorption and metabolic priming. Don't waste it on empty calories.",
        "actions": [
            "💧 Drink 500ml of water before anything else — you just went 7+ hours without hydration.",
            "🥚 Front-load protein within 60 minutes of waking to blunt the cortisol-muscle breakdown cycle.",
            "☕ If you're having coffee, delay it 90 minutes post-wake to let cortisol do its job naturally."
        ]
    },
    "mid_morning": {  # 09:00–11:59
        "emoji": "⚡",
        "title": "Peak Cognitive Window — Don't Crash It",
        "message": "Your brain is running at peak capacity right now. What you eat in this window either extends that sharpness or kills it by noon. Choose precision over convenience.",
        "actions": [
            "🥜 If hunger hits, opt for nuts or a boiled egg — slow-burn fuel that won't spike insulin.",
            "🚫 Skip the muffin or fruit juice — the sugar crash arrives exactly when you need focus most.",
            "💧 Keep water intake consistent — even mild dehydration drops cognitive performance by 10–15%."
        ]
    },
    "pre_lunch": {  # 12:00–13:59
        "emoji": "☀️",
        "title": "Midday Refuel Protocol",
        "message": "Lunch isn't just calories — it's your metabolic mid-point. What you load here dictates your afternoon energy curve. A high-carb lunch is a productivity suicide note.",
        "actions": [
            "🥗 Build your plate as: half vegetables, a quarter lean protein, a quarter complex carbs.",
            "🐟 Fish, legumes, or chicken over red meat — you want alert, not sedated.",
            "🚫 Avoid fried, heavy, or sauce-loaded meals — the digestive load will steal blood from your brain."
        ]
    },
    "afternoon": {  # 14:00–16:59
        "emoji": "☀️",
        "title": "The 3 PM Slump Prevention",
        "message": "Don't fall into the sugar-trap. The mid-afternoon crash is just a bad carb choice away. Your insulin is sensitive right now — exploit it smartly or pay the price in fog.",
        "actions": [
            "🥜 A handful of raw nuts or seeds — high-density, clean-burning fats that don't spike your glucose.",
            "🚶 Stand up and get 5 minutes of natural sunlight to reset your circadian clock and cortisol baseline.",
            "🍵 Green tea over coffee if you need a lift — L-theanine keeps you alert without the 4 PM anxiety spiral."
        ]
    },
    "pre_dinner": {  # 17:00–19:59
        "emoji": "🍽️",
        "title": "Dinner Engineering Window",
        "message": "You're heading into the last major fueling event of the day. Your metabolism is slowing. Don't load the tank if you're just parking in the garage — but if you've been active, you've earned the refuel.",
        "actions": [
            "🥦 Make vegetables non-negotiable at this meal — they set the fibre baseline for overnight gut work.",
            "🐟 Prioritise amino acids that support nighttime recovery and growth hormone release — fish, eggs, cottage cheese.",
            "🕖 Try to eat before 7:30 PM — late eating compresses your overnight fasting window and disrupts sleep quality."
        ]
    },
    "evening": {  # 20:00–22:59
        "emoji": "🌙",
        "title": "Night Operations Strategy",
        "message": "Winding down requires structural macro management. Your insulin sensitivity drops at night — carbs consumed now convert to fat far more readily than earlier in the day.",
        "actions": [
            "🍵 Swap dessert for a hot magnesium-rich herbal tea — signals sleep readiness and reduces overnight cortisol.",
            "🚫 Avoid processed snacks, alcohol, or high-sodium foods — all disrupt sleep architecture.",
            "🥛 If genuinely hungry, casein protein (cottage cheese, Greek yogurt) feeds muscles through the night without spiking insulin."
        ]
    },
    "late_night": {  # 23:00–04:59
        "emoji": "🌚",
        "title": "Overnight Fasting Zone",
        "message": "This is your metabolic repair window. Every hour of fasting here allows cellular cleanup (autophagy) and fat metabolism. Eating now resets the clock and costs you the benefits.",
        "actions": [
            "💧 Water only if you must have something — hunger at this hour is usually dehydration or habit.",
            "🚫 Hard no to alcohol, sugar, or high-fat snacks — they suppress growth hormone release during deep sleep.",
            "😴 Focus on sleep quality — melatonin, darkness, and cool temperatures beat any supplement."
        ]
    }
}

ACTIVITY_RECS = {
    "intense": {
        "emoji": "🔥",
        "title": "Intense Output Detected — Rebuild Mode",
        "message": lambda steps, cal_burn, total_target, cal_gap: (
            f"You've torched {cal_burn:.0f} active calories today ({steps:,} steps). "
            f"Your body is in a catabolic state right now — if you don't feed the recovery, "
            f"you're breaking down muscle for fuel. Adjusted target: {total_target:.0f} kcal. "
            f"You still need {cal_gap:.0f} kcal to close the gap."
        ),
        "actions": [
            "🥩 Prioritise a complete protein source within 45 minutes of your last activity — the anabolic window is real.",
            "🍚 Complex carbs are mandatory tonight — brown rice, sweet potato, or oats to replenish glycogen stores.",
            "🥑 Add healthy fats to slow absorption and sustain overnight recovery — avocado, olive oil, or nuts.",
            "💧 You're likely still dehydrated — minimum 500ml more water before sleep, electrolytes if you sweated heavily."
        ]
    },
    "active": {
        "emoji": "⚡",
        "title": "Solid Active Day — Maintain the Edge",
        "message": lambda steps, cal_burn, total_target, cal_gap: (
            f"{steps:,} steps and {cal_burn:.0f} kcal burned — you've earned a proper refuel. "
            f"Adjusted calorie ceiling: {total_target:.0f} kcal. Remaining: {cal_gap:.0f} kcal. "
            f"Don't undercut recovery by eating too light."
        ),
        "actions": [
            "🥗 A balanced dinner with protein, colourful vegetables, and wholegrains covers your bases.",
            "🍌 A piece of fruit makes an ideal post-activity snack — natural sugars replenish liver glycogen fast.",
            "💧 Hydration window is still open — keep sipping consistently rather than gulping all at once."
        ]
    },
    "moderate": {
        "emoji": "🚶",
        "title": "Moderate Day — Steady as She Goes",
        "message": lambda steps, cal_burn, total_target, cal_gap: (
            f"{steps:,} steps · {cal_burn:.0f} kcal burned. "
            f"You're in the maintenance zone. Remaining today: {cal_gap:.0f} kcal. "
            f"Eat to your actual output — not your ambition."
        ),
        "actions": [
            "🥦 Fill at least half your dinner plate with non-starchy vegetables — density without caloric load.",
            "🍗 Lean protein portion roughly the size of your palm — adequate but not excessive for this output level.",
            "🚫 Skip the extra bread, sauce, or dessert tonight — you haven't generated the deficit to absorb it cleanly."
        ]
    },
    "light": {
        "emoji": "😊",
        "title": "Light Day — Calibrate Accordingly",
        "message": lambda steps, cal_burn, total_target, cal_gap: (
            f"Only {steps:,} steps and {cal_burn:.0f} kcal burned today. "
            f"Your energy demand is low — eating to a higher target than your output creates a surplus. "
            f"Remaining: {cal_gap:.0f} kcal."
        ),
        "actions": [
            "🥗 Keep dinner light and nutrient-dense — salads with legumes, grilled fish, or soups with vegetables.",
            "🚫 Avoid high-carb, high-fat combinations tonight — your muscles aren't primed to absorb the glycogen load.",
            "🚶 Even a 15-minute post-dinner walk improves insulin sensitivity and helps clear blood glucose."
        ]
    },
    "sedentary": {
        "emoji": "💺",
        "title": "Sedentary Day — Don't Eat Like You Weren't",
        "message": lambda steps, cal_burn, total_target, cal_gap: (
            f"Only {steps:,} steps so far. Your body hasn't demanded much fuel today — "
            f"overfeeding a sedentary day is how caloric debt builds quietly. "
            f"Remaining: {cal_gap:.0f} kcal."
        ),
        "actions": [
            "🚶 Take a 20-minute walk after your next meal — it's the single highest-ROI intervention for metabolic health.",
            "🥗 Light dinner: leafy greens, lean protein, minimal processed carbs.",
            "🚫 No heavy pasta, pizza, or alcohol tonight — your insulin sensitivity is already blunted from low movement.",
            "💧 Drink water before reaching for snacks — sedentary hunger is often just boredom or mild dehydration."
        ]
    }
}

NUTRIENT_GAP_RECS = {
    "protein_deficit": {
        "emoji": "💪",
        "title": "Protein Deficit — Muscle Cannibalism Risk",
        "message": lambda consumed, target: (
            f"You're at {consumed:.0f}g protein against a {target}g target. "
            f"If you don't supply the building blocks, your body will happily cannibalize its own muscle tissue for amino requirements. "
            f"This compounds especially hard on active days."
        ),
        "actions": [
            "🥚 3 whole eggs, a cup of Greek yogurt, or 150g of cottage cheese — get it in now.",
            "🍗 Your next major meal needs to double the normal protein footprint.",
            "🥜 Edamame, lentils, or a quality protein snack as a bridge if mealtime is hours away."
        ]
    },
    "protein_deficit_intense": {  # Combo: intense activity + low protein
        "emoji": "🚨",
        "title": "Critical: High Output, No Recovery Fuel",
        "message": lambda consumed, target: (
            f"You burned hard today but you're only at {consumed:.0f}g protein (target: {target}g). "
            f"Without adequate amino acids post-exercise, muscle protein synthesis shuts down and catabolism takes over. "
            f"This is the scenario that makes training counterproductive."
        ),
        "actions": [
            "🥩 Prioritise a complete protein meal immediately — chicken, fish, steak, or eggs.",
            "🥛 A casein shake or cottage cheese before bed extends muscle protein synthesis through the night.",
            "⚠️ Don't go to sleep under-fuelled on a high-output day — recovery happens overnight, not at the gym."
        ]
    },
    "fibre_deficit": {
        "emoji": "🌿",
        "title": "Microbiome Running on Empty",
        "message": lambda consumed, target: (
            f"Only {consumed:.0f}g fibre against a {target}g target. "
            f"Your gut bacteria are running out of prebiotics to ferment into short-chain fatty acids — "
            f"the compounds that regulate inflammation, immunity, and even mood. Fix the plumbing."
        ),
        "actions": [
            "🥦 Load your next meal with broccoli, chia seeds, or lentils — density counts here.",
            "🍎 Eat whole fruits with the skin intact to capture structural fibres your gut bacteria actually need.",
            "🌾 Swap white rice or bread for a wholegrain equivalent — one meal change closes a significant gap."
        ]
    },
    "calcium_deficit": {
        "emoji": "🦴",
        "title": "Calcium Deficit — Silent Bone Tax",
        "message": lambda consumed, target: (
            f"At {consumed:.0f}mg calcium (target: {target}mg), your body will pull what it needs from bone reserves. "
            f"It's a silent process you won't feel until it matters. Dietary calcium is non-negotiable."
        ),
        "actions": [
            "🥛 A glass of dairy milk or fortified plant milk covers 25–30% of daily needs in one move.",
            "🥬 Kale, bok choy, and broccoli are surprisingly calcium-dense and come with fibre bonuses.",
            "🧀 A small serve of hard cheese at your next meal is a calorie-efficient calcium hit."
        ]
    },
    "iron_deficit": {
        "emoji": "🩸",
        "title": "Iron Low — Oxygen Delivery Compromised",
        "message": lambda consumed, target: (
            f"Iron is at {consumed:.0f}mg against a {target}mg target. "
            f"Low iron doesn't just cause fatigue — it reduces oxygen-carrying capacity, "
            f"meaning every physical and cognitive task runs on a throttled engine."
        ),
        "actions": [
            "🥩 Red meat 2–3x per week is the highest-bioavailability iron source available.",
            "🥬 Spinach and lentils offer plant-based iron, but pair them with vitamin C to triple absorption rate.",
            "☕ Avoid tea or coffee within an hour of iron-rich meals — tannins block absorption significantly."
        ]
    },
    "vitamin_c_deficit": {
        "emoji": "🍊",
        "title": "Vitamin C Gap — Immunity & Collagen at Risk",
        "message": lambda consumed, target: (
            f"Only {consumed:.0f}mg vitamin C logged (target: {target}mg). "
            f"Beyond immunity, vitamin C is the rate-limiting factor in collagen synthesis — "
            f"which means skin, joint, and tissue integrity all depend on adequate daily intake."
        ),
        "actions": [
            "🥝 One kiwifruit delivers your entire daily C requirement in a 60-calorie package.",
            "🫑 Raw capsicum (red or yellow) has 3x the vitamin C of an orange — add it to any meal.",
            "🍓 A cup of strawberries with your next snack closes the gap without touching calorie targets."
        ]
    },
    "sodium_excess": {
        "emoji": "⚠️",
        "title": "Sodium Overload — Vascular Pressure Rising",
        "message": lambda consumed, target: (
            f"You're at {consumed:.0f}mg sodium against a {target}mg limit. "
            f"Excess sodium isn't just a blood pressure issue — it actively dehydrates cells, "
            f"causes water retention, and disrupts sleep quality. The damage compounds daily."
        ),
        "actions": [
            "💧 Increase water intake immediately — helps the kidneys flush excess sodium through urine.",
            "🚫 No more processed food, sauces, or added salt for the rest of today — you've already hit the ceiling.",
            "🥦 High-potassium foods (banana, sweet potato, leafy greens) actively counteract sodium's vascular effects."
        ]
    },
    "cholesterol_excess": {
        "emoji": "💛",
        "title": "Cholesterol Above Threshold",
        "message": lambda consumed, target: (
            f"At {consumed:.0f}mg dietary cholesterol (limit: {target}mg), you're over the recommended ceiling. "
            f"While dietary cholesterol impact varies individually, consistent excess correlates with elevated LDL in most populations."
        ),
        "actions": [
            "🚫 Limit egg yolks, organ meats, and full-fat dairy for the rest of today.",
            "🐟 Swap red meat for fish at your next meal — omega-3s actively improve your lipid profile.",
            "🥑 Monounsaturated fats (avocado, olive oil) help raise HDL to offset LDL elevation."
        ]
    },
    "calories_under": {
        "emoji": "🔋",
        "title": "Calorie Deficit — Running Below Threshold",
        "message": lambda consumed, target: (
            f"Only {consumed:.0f} of {target} kcal consumed. "
            f"A moderate deficit is fine — but fall too far below and your body down-regulates metabolism "
            f"and starts protecting fat stores by burning lean mass instead. Eat enough."
        ),
        "actions": [
            "🥑 Add calorie-dense but nutrient-rich foods — nuts, olive oil, avocado, eggs.",
            "🍚 A proper carb-protein meal closes a calorie gap fast without relying on junk.",
            "🚫 Don't solve this with empty calories — the goal is nutrient density, not just filling numbers."
        ]
    },
    "calories_over": {
        "emoji": "🛑",
        "title": "Caloric Ceiling Breached",
        "message": lambda consumed, target: (
            f"You've consumed {consumed:.0f} kcal against a {target} kcal target — "
            f"that's {consumed - target:.0f} kcal over. Depending on your output today, "
            f"this may or may not matter. But the compounding effect of daily surpluses is fat storage."
        ),
        "actions": [
            "🚫 No more high-calorie additions today — snacks, sauces, or alcohol all count.",
            "🥗 If still hungry, fill up on raw vegetables or clear broth — volume without caloric cost.",
            "🚶 30 minutes of brisk walking burns ~150–200 kcal and partially offsets the surplus."
        ]
    }
}

MEAL_TIMING_RECS = {
    "dinner_large_gap": {
        "emoji": "🍽️",
        "title": "Dinner Brief — You Have Room to Work With",
        "message": lambda cal_gap, level: (
            f"{cal_gap:.0f} kcal remaining. With a {level} activity day, "
            f"here are three dinner strategies ranked by recovery value:"
        ),
        "options": {
            "intense":  [
                "🥩 Grilled salmon (180g) + roasted sweet potato + steamed greens — ~620 kcal, 45g protein. Peak recovery meal.",
                "🍗 Chicken stir-fry with broccoli, capsicum, and brown rice — ~550 kcal, 42g protein. Glycogen + protein combo.",
                "🥚 4-egg omelette with spinach, feta, and a slice of sourdough — ~480 kcal, 36g protein. Fast and clean."
            ],
            "active":   [
                "🐟 Baked cod + roasted vegetables + quinoa — ~480 kcal, 38g protein. Clean macro split.",
                "🍗 Grilled chicken with a large salad and tahini dressing — ~440 kcal, 40g protein.",
                "🌱 Lentil dhal with spinach and wholegrain roti — ~420 kcal, 22g protein. High fibre bonus."
            ],
            "moderate": [
                "🥗 Buddha bowl: brown rice, chickpeas, roasted vegetables, avocado — ~480 kcal, 18g protein.",
                "🐟 Poached salmon with a green salad and olive oil dressing — ~420 kcal, 35g protein.",
                "🍜 Vegetable soup with lentils and a slice of multigrain bread — ~350 kcal, 18g protein."
            ],
            "default":  [
                "🥗 A balanced plate: lean protein + vegetables + complex carbs.",
                "🍲 Soups or stews with legumes — high satiety, controlled calories.",
                "🌿 Plant-forward meal if you've had animal protein earlier in the day."
            ]
        }
    },
    "dinner_small_gap": {
        "emoji": "⚠️",
        "title": "Light Dinner Only — You're Close to Your Ceiling",
        "message": lambda cal_gap: (
            f"Only {cal_gap:.0f} kcal remaining for the day. Keep dinner structured and minimal."
        ),
        "actions": [
            "🥗 Large salad with a palm-sized portion of grilled protein — fills you up without overspending.",
            "🍲 Clear broth-based soup with vegetables — maximum volume, minimal caloric cost.",
            "🚫 No bread, rice, pasta, or dessert tonight — you don't have the budget."
        ]
    },
    "no_lunch_logged": {
        "emoji": "☀️",
        "title": "No Lunch Recorded — Skipping or Forgot to Log?",
        "message": "It's past midday and no lunch is logged. Skipping meals tends to produce compensatory overeating later — and the food choices get worse the hungrier you get.",
        "actions": [
            "📸 Log what you ate even if you've already finished — back-fill keeps your day accurate.",
            "🥗 If you genuinely haven't eaten, have a balanced meal now rather than waiting for dinner.",
            "⏰ Skipping lunch on high-activity days actively impairs afternoon performance and recovery."
        ]
    }
}


# ─── Rebuilt Core Recommendation Engine ───────────────────────────────────────

def get_time_slot(hour):
    if   5  <= hour <= 8:  return "early_morning"
    elif 9  <= hour <= 11: return "mid_morning"
    elif 12 <= hour <= 13: return "pre_lunch"
    elif 14 <= hour <= 16: return "afternoon"
    elif 17 <= hour <= 19: return "pre_dinner"
    elif 20 <= hour <= 22: return "evening"
    else:                  return "late_night"


def get_smart_recommendations(fitness_data, daily_totals, daily_targets, timeline):
    if not fitness_data.get("available"):
        return get_basic_recommendations(daily_totals, daily_targets, timeline)

    steps        = fitness_data.get("steps", 0)
    cal_burn     = fitness_data.get("calories_burned", 0)
    level        = fitness_data.get("activity_level", "sedentary")
    hour         = datetime.now().hour
    cal_consumed = daily_totals.get("calories", 0)
    base_target  = daily_targets.get("calories", 2000)
    total_target = base_target + cal_burn
    cal_gap      = round(total_target - cal_consumed, 0)
    time_slot    = get_time_slot(hour)

    recs = []

    # ── 1. Activity-level card ────────────────────────────────────────────────
    act = ACTIVITY_RECS[level]
    recs.append({
        "type":     "activity",
        "emoji":    act["emoji"],
        "title":    act["title"],
        "message":  act["message"](steps, cal_burn, total_target, cal_gap),
        "actions":  act["actions"],
        "priority": "high" if level in ("intense", "sedentary") else "medium"
    })

    # ── 2. Time-of-day contextual card ───────────────────────────────────────
    ts = TIME_SLOT_RECS[time_slot]
    recs.append({
        "type":     "timing",
        "emoji":    ts["emoji"],
        "title":    ts["title"],
        "message":  ts["message"],
        "actions":  ts["actions"],
        "priority": "medium"
    })

    # ── 3. Meal timing window cards ───────────────────────────────────────────
    if 16 <= hour <= 20:
        if cal_gap > 400:
            mt   = MEAL_TIMING_RECS["dinner_large_gap"]
            opts = mt["options"].get(level, mt["options"]["default"])
            recs.append({
                "type":     "meal_timing",
                "emoji":    mt["emoji"],
                "title":    mt["title"],
                "message":  mt["message"](cal_gap, level),
                "actions":  opts,
                "priority": "high"
            })
        elif cal_gap < 200:
            mt = MEAL_TIMING_RECS["dinner_small_gap"]
            recs.append({
                "type":     "meal_timing",
                "emoji":    mt["emoji"],
                "title":    mt["title"],
                "message":  mt["message"](cal_gap),
                "actions":  mt["actions"],
                "priority": "medium"
            })

    if hour >= 13 and not any(
        e.get("category") == "Lunch" for block in timeline for e in [block]
    ):
        mt = MEAL_TIMING_RECS["no_lunch_logged"]
        recs.append({
            "type":     "meal_timing",
            "emoji":    mt["emoji"],
            "title":    mt["title"],
            "message":  mt["message"],
            "actions":  mt["actions"],
            "priority": "medium"
        })

    # ── 4. Nutrient gap cards ─────────────────────────────────────────────────
    protein_consumed = daily_totals.get("protein", 0)
    protein_target   = daily_targets.get("protein", 50)
    if protein_consumed < protein_target * 0.65 and hour >= 12:
        # Escalate to critical if also intense activity day
        key = "protein_deficit_intense" if level == "intense" else "protein_deficit"
        ng  = NUTRIENT_GAP_RECS[key]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](protein_consumed, protein_target),
            "actions":  ng["actions"],
            "priority": "high" if level in ("intense", "active") else "medium"
        })

    fibre_consumed = daily_totals.get("fibre", 0)
    if fibre_consumed < 15 and hour >= 14:
        ng = NUTRIENT_GAP_RECS["fibre_deficit"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](fibre_consumed, daily_targets.get("fibre", 30)),
            "actions":  ng["actions"],
            "priority": "medium"
        })

    calcium_consumed = daily_totals.get("calcium", 0)
    if calcium_consumed < daily_targets.get("calcium", 1000) * 0.5 and hour >= 15:
        ng = NUTRIENT_GAP_RECS["calcium_deficit"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](calcium_consumed, daily_targets.get("calcium", 1000)),
            "actions":  ng["actions"],
            "priority": "low"
        })

    iron_consumed = daily_totals.get("iron", 0)
    if iron_consumed < daily_targets.get("iron", 18) * 0.5 and hour >= 15:
        ng = NUTRIENT_GAP_RECS["iron_deficit"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](iron_consumed, daily_targets.get("iron", 18)),
            "actions":  ng["actions"],
            "priority": "low"
        })

    vc_consumed = daily_totals.get("vitamin_c", 0)
    if vc_consumed < daily_targets.get("vitamin_c", 90) * 0.5 and hour >= 15:
        ng = NUTRIENT_GAP_RECS["vitamin_c_deficit"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](vc_consumed, daily_targets.get("vitamin_c", 90)),
            "actions":  ng["actions"],
            "priority": "low"
        })

    sodium_consumed = daily_totals.get("sodium", 0)
    if sodium_consumed > daily_targets.get("sodium", 2300):
        ng = NUTRIENT_GAP_RECS["sodium_excess"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](sodium_consumed, daily_targets.get("sodium", 2300)),
            "actions":  ng["actions"],
            "priority": "caution"
        })

    chol_consumed = daily_totals.get("cholesterol", 0)
    if chol_consumed > daily_targets.get("cholesterol", 300):
        ng = NUTRIENT_GAP_RECS["cholesterol_excess"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](chol_consumed, daily_targets.get("cholesterol", 300)),
            "actions":  ng["actions"],
            "priority": "caution"
        })

    # Calorie extremes
    if cal_consumed > 0:
        pct = cal_consumed / total_target
        if pct < 0.55 and hour >= 16:
            ng = NUTRIENT_GAP_RECS["calories_under"]
            recs.append({
                "type":     "nutrient",
                "emoji":    ng["emoji"],
                "title":    ng["title"],
                "message":  ng["message"](cal_consumed, total_target),
                "actions":  ng["actions"],
                "priority": "medium"
            })
        elif pct > 1.15:
            ng = NUTRIENT_GAP_RECS["calories_over"]
            recs.append({
                "type":     "nutrient",
                "emoji":    ng["emoji"],
                "title":    ng["title"],
                "message":  ng["message"](cal_consumed, total_target),
                "actions":  ng["actions"],
                "priority": "caution"
            })

    # ── Sort: high → medium → caution → low ──────────────────────────────────
    order = {"high": 0, "medium": 1, "caution": 2, "low": 3}
    recs.sort(key=lambda r: order.get(r.get("priority", "low"), 4))

    return {
        "available":        True,
        "cal_burned":       cal_burn,
        "cal_consumed":     round(cal_consumed, 0),
        "cal_target_adj":   round(total_target, 0),
        "cal_remaining":    round(cal_gap, 0),
        "steps":            steps,
        "activity_level":   level,
        "activity_label":   fitness_data.get("activity_label", ""),
        "activity_emoji":   fitness_data.get("activity_emoji", ""),
        "recommendations":  recs
    }


def get_basic_recommendations(daily_totals, daily_targets, timeline):
    """Fallback when Google Fit is unavailable — still uses the rich copy library."""
    cal_consumed = daily_totals.get("calories", 0)
    cal_target   = daily_targets.get("calories", 2000)
    cal_gap      = cal_target - cal_consumed
    hour         = datetime.now().hour
    time_slot    = get_time_slot(hour)
    recs         = []

    # Always include time-of-day rec
    ts = TIME_SLOT_RECS[time_slot]
    recs.append({
        "type":     "timing",
        "emoji":    ts["emoji"],
        "title":    ts["title"],
        "message":  ts["message"],
        "actions":  ts["actions"],
        "priority": "medium"
    })

    if cal_consumed == 0 and hour >= 12:
        recs.insert(0, {
            "type":     "reminder",
            "emoji":    "📝",
            "title":    "No Meals Logged Yet Today",
            "message":  "Start logging your meals to unlock personalised recommendations. Tracking accuracy is the foundation of everything else.",
            "actions":  ["📸 Take a photo of your next meal to begin tracking."],
            "priority": "high"
        })
    elif cal_gap > 500:
        ng = NUTRIENT_GAP_RECS["calories_under"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](cal_consumed, cal_target),
            "actions":  ng["actions"],
            "priority": "medium"
        })
    elif cal_gap < -200:
        ng = NUTRIENT_GAP_RECS["calories_over"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](cal_consumed, cal_target),
            "actions":  ng["actions"],
            "priority": "caution"
        })

    # Still check nutrient gaps even without Fit data
    protein_consumed = daily_totals.get("protein", 0)
    if protein_consumed < daily_targets.get("protein", 50) * 0.65 and hour >= 13:
        ng = NUTRIENT_GAP_RECS["protein_deficit"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](protein_consumed, daily_targets.get("protein", 50)),
            "actions":  ng["actions"],
            "priority": "medium"
        })

    fibre_consumed = daily_totals.get("fibre", 0)
    if fibre_consumed < 15 and hour >= 14:
        ng = NUTRIENT_GAP_RECS["fibre_deficit"]
        recs.append({
            "type":     "nutrient",
            "emoji":    ng["emoji"],
            "title":    ng["title"],
            "message":  ng["message"](fibre_consumed, daily_targets.get("fibre", 30)),
            "actions":  ng["actions"],
            "priority": "medium"
        })

    order = {"high": 0, "medium": 1, "caution": 2, "low": 3}
    recs.sort(key=lambda r: order.get(r.get("priority", "low"), 4))

    return {
        "available":        False,
        "cal_consumed":     round(cal_consumed, 0),
        "cal_target_adj":   cal_target,
        "cal_remaining":    round(cal_gap, 0),
        "recommendations":  recs
    }
 ###-----------------------
def get_google_credentials():
    """
    Load and auto-refresh Google credentials.
    Priority: local token file → env variable → error
    """
    creds = None

    # Load client secrets
    secrets_path = os.path.join(os.path.dirname(__file__), 'client_secrets.json')
    if not os.path.exists(secrets_path):
        return None, "client_secrets.json not found"

    with open(secrets_path, 'r') as f:
        secrets_data = json.load(f)
        client_config = secrets_data.get('web') or secrets_data.get('installed', {})

    def fix_token_data(token_data):
        """Safely maps fields to match exactly what Google library expects"""
        # Copy values rather than popping to avoid reference losses
        if 'token' in token_data:
            token_data['access_token'] = token_data.get('token')
        
        # Ensure scopes format is a space separated string if provided as a list
        if isinstance(token_data.get('scopes'), list):
            token_data['scopes'] = ' '.join(token_data['scopes'])
            
        # Guarantee client configurations are injected directly from client_secrets.json
        token_data['client_id']     = client_config.get('client_id')
        token_data['client_secret'] = client_config.get('client_secret')
        token_data['token_uri']     = client_config.get('token_uri', 'https://oauth2.googleapis.com/token')

        print(f"DEBUG token_data: has_access={bool(token_data.get('access_token'))}, has_refresh={bool(token_data.get('refresh_token'))}")
        return token_data

    # Option 1 — Load from local token file (preferred)
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
            token_data = fix_token_data(token_data)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            print("Loaded credentials from google_token.json")
        except Exception as e:
            print(f"Token file load failed: {e}")
            creds = None

    # Option 2 — Fall back to env variable
    if not creds:
        raw_env = os.getenv('TOKEN_JSON_ENV', '').strip()
        if raw_env.startswith(("'", '"')) and raw_env.endswith(("'", '"')):
            raw_env = raw_env[1:-1]
        if raw_env:
            try:
                token_data = json.loads(raw_env)
                token_data = fix_token_data(token_data)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                print("Loaded credentials from TOKEN_JSON_ENV")
            except Exception as e:
                return None, f"Failed to parse TOKEN_JSON_ENV: {e}"

    if not creds:
        return None, "No credentials found. Set TOKEN_JSON_ENV or google_token.json"

    # Auto-refresh if expired
    if not creds.valid:
        if creds.refresh_token:
            try:
                print("Access token expired — auto refreshing via token pipeline...")
                creds.refresh(Request())
                
                # Save refreshed token safely back to local storage
                with open(TOKEN_FILE, 'w') as f:
                    f.write(creds.to_json())
                print(f"✅ Token refreshed and written successfully to {TOKEN_FILE}")
            except Exception as e:
                print(f"❌ Refresh FAILED: {e}")
                return None, f"Token refresh failed: {e}"
        else:
            print(f"❌ Cannot refresh: expired={creds.expired}, has_refresh={bool(creds.refresh_token)}")
            return None, "Token missing refresh_token property. Re-run your terminal authentication script."

    return creds, None

@app.route('/fitness', methods=['GET'])
def fitness():
    """Return fitness data + smart recommendations"""
    try:
        fitness_data = get_fitness_data()

        # Get today's nutrition totals
        today = datetime.now().strftime("%Y-%m-%d")
        daily_totals = {k: 0.0 for k in DAILY_TARGETS}

        if os.path.exists('meals_log.json'):
            with open('meals_log.json') as f:
                log = json.load(f)
            day_meals = [m for m in log
                        if m.get('timestamp','').startswith(today)
                        or m.get('date','') == today]
            for meal in day_meals:
                for food in meal.get('foods', []):
                    daily_totals['calories']   += food.get('calories', 0) or 0
                    daily_totals['protein']    += food.get('protein', 0) or 0
                    daily_totals['carbs']      += food.get('carbs', 0) or 0
                    daily_totals['fat']        += food.get('fat', 0) or 0
                    daily_totals['fibre']      += food.get('fibre', 0) or 0
                    daily_totals['sodium']     += food.get('sodium', 0) or 0
                    daily_totals['calcium']    += food.get('calcium', 0) or 0
                    daily_totals['iron']       += food.get('iron', 0) or 0
                    daily_totals['potassium']  += food.get('potassium', 0) or 0
                    daily_totals['vitamin_c']  += food.get('vitamin_c', 0) or 0
                    daily_totals['cholesterol']+= food.get('cholesterol', 0) or 0

        recs = get_smart_recommendations(
            fitness_data, daily_totals, DAILY_TARGETS, []
        )

        return jsonify({
            "fitness":         fitness_data,
            "recommendations": recs
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/fitness/debug', methods=['GET'])
def fitness_debug():
    """List all available data sources"""
    try:
        creds, error = get_google_credentials()
        if error:
            return jsonify({"error": error})
        service = build('fitness', 'v1', credentials=creds)
        sources = service.users().dataSources().list(userId='me').execute()
        cal_sources = [
            {
                "dataStreamId": s.get("dataStreamId"),
                "dataTypeName": s.get("dataType", {}).get("name"),
                "device":       s.get("device", {}).get("model", "unknown")
            }
            for s in sources.get("dataSource", [])
            if "calorie" in s.get("dataType", {}).get("name", "").lower()
            or "bmr" in s.get("dataType", {}).get("name", "").lower()
        ]
        return jsonify({
            "calorie_sources": cal_sources,
            "total_sources":   len(sources.get("dataSource", []))
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# @app.route('/fitness/debug', methods=['GET'])
# def fitness_debug():
#     """List all available data sources in your Google Fit account"""
#     try:
#         creds, error = get_google_credentials()
#         if error:
#             return jsonify({"error": error})

#         service = build('fitness', 'v1', credentials=creds)

#         # List all data sources
#         sources = service.users().dataSources().list(userId='me').execute()

#         # Filter calorie related ones
#         cal_sources = [
#             {
#                 "dataStreamId": s.get("dataStreamId"),
#                 "dataTypeName": s.get("dataType", {}).get("name"),
#                 "device":       s.get("device", {}).get("model", "unknown")
#             }
#             for s in sources.get("dataSource", [])
#             if "calorie" in s.get("dataType", {}).get("name", "").lower()
#             or "bmr" in s.get("dataType", {}).get("name", "").lower()
#         ]

#         return jsonify({
#             "calorie_sources": cal_sources,
#             "total_sources":   len(sources.get("dataSource", []))
#         })

#     except Exception as e:
#         return jsonify({"error": str(e)})

# ── 2. Add a PIN validation route ────────────────────────────────────────────

# In app.py — update only validate_pin route
# Keep this as safety net
@app.route('/auth/validate', methods=['POST'])
def validate_pin():
    data = request.get_json() or {}
    pin  = data.get('pin', '').strip()

    # Try Supabase first (dynamic patients)
    try:
        from supabase_db import validate_pin as db_validate_pin
        patient = db_validate_pin(pin)
        if patient:
            patient_id = patient['name'].lower().replace(' ', '_')
            return jsonify({
                "valid":      True,
                "patient_id": patient_id,
                "name":       patient['name'],
                "message":    "Access granted"
            })
    except Exception as e:
        print(f'Supabase error, using fallback: {e}')

    # Fallback to hardcoded PINs (demo safety net)
    patient_id = VALID_PINS.get(pin)
    if patient_id:
        return jsonify({
            "valid":      True,
            "patient_id": patient_id,
            "name":       patient_id.title(),
            "message":    "Access granted (offline mode)"
        })

    return jsonify({"valid": False, "error": "Invalid PIN"}), 401

@app.before_request
def global_pin_check():
    open_paths     = ['/static/', '/auth/', '/reset']
    open_endpoints = ['index', 'static']

    if request.endpoint in open_endpoints:
        return None
    if any(request.path.startswith(p) for p in open_paths):
        return None

    pin = (
        request.headers.get('X-App-Pin') or
        request.args.get('pin') or
        (request.get_json(silent=True) or {}).get('pin') or
        ''
    ).strip()

    # Try Supabase first
    try:
        from supabase_db import validate_pin as db_validate_pin
        if db_validate_pin(pin):
            return None
    except Exception as e:
        print(f'Supabase auth error: {e}')

    # Fallback to hardcoded PINs
    if pin in VALID_PINS:
        return None

    return jsonify({
        "error": "Invalid PIN",
        "code":  "AUTH_FAILED"
    }), 401

if __name__ == '__main__':
    # Initialize cache memory pool right before bootup
    load_embeddings_into_cache()
    app.run(host='0.0.0.0', port=5000, debug=True)