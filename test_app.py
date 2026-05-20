# Food Analyzer - Flask Web App
# Author: Sanyam
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
try:
    import tiktoken
except Exception:
    tiktoken = None
import requests
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, g
from dotenv import load_dotenv
# import inspect

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
SUPPORTED_PROVIDERS = {"gemini", "claude", "openai"}
print("DEBUG: GEMINI_API_KEY loaded:", "YES" if GEMINI_API_KEY else "NO")
print("DEBUG: CLAUDE_API_KEY loaded:", "YES" if CLAUDE_API_KEY else "NO")
print("DEBUG: OPENAI_API_KEY loaded:", "YES" if OPENAI_API_KEY else "NO")
print("DEBUG: DEFAULT AI_PROVIDER:", AI_PROVIDER)

# # Vector search imports
# try:
#     import chromadb
#     from sentence_transformers import SentenceTransformer
#     VECTOR_SEARCH_AVAILABLE = True
# except ImportError:
#     VECTOR_SEARCH_AVAILABLE = False
#     print("WARNING: chromadb or sentence-transformers not installed")

# USE_VECTOR_SEARCH = os.getenv("USE_VECTOR_SEARCH", "false").lower() == "true"
# print(f"DEBUG: VECTOR_SEARCH_AVAILABLE={VECTOR_SEARCH_AVAILABLE}, USE_VECTOR_SEARCH={USE_VECTOR_SEARCH}")
# ── Vector search imports ─────────────────────────
# ── ChromaDB import (Windows only) ───────────────
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("WARNING: chromadb not installed (OK on mobile)")

# ── SentenceTransformer (both Windows + Mobile) ──
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("WARNING: sentence-transformers not installed")

# ── Qdrant import ─────────────────────────────────
try:
    from qdrant_client import QdrantClient
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    print("WARNING: qdrant-client not installed")

USE_QDRANT = os.getenv("USE_QDRANT", "false").lower() == "true"
QDRANT_COLLECTION = "food_analyzer"
CHROMA_PATH = "./food_vectors"

# ── Globals ───────────────────────────────────────
qdrant_client_instance = None
chroma_collection = None
embedding_model = None  # shared by both ChromaDB and Qdrant

def init_vector_search():
    global qdrant_client_instance, chroma_collection, embedding_model

    # Always load embedding model — used by both
    if SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            print("🧠 Loading embedding model...")
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ Embedding model ready!")
        except Exception as e:
            print(f"⚠️ Embedding model failed: {e}")
            return
    else:
        print("⚠️ sentence-transformers not available!")
        return

    if USE_QDRANT:
        # ── Qdrant Cloud ──────────────────────────
        if not QDRANT_AVAILABLE:
            print("⚠️ qdrant-client not installed!")
            return
        try:
            print("🔗 Connecting to Qdrant Cloud...")
            qdrant_client_instance = QdrantClient(
                url=os.getenv("QDRANT_URL"),
                api_key=os.getenv("QDRANT_API_KEY"),
                prefer_grpc=False
            )
            count = qdrant_client_instance.count(QDRANT_COLLECTION).count
            print(f"✅ Qdrant ready — {count} foods in cloud!")
        except Exception as e:
            print(f"⚠️ Qdrant connection failed: {e}")

    else:
        # ── ChromaDB Local ────────────────────────
        if not CHROMADB_AVAILABLE:
            print("⚠️ chromadb not installed!")
            return
        try:
            print("📂 Loading ChromaDB local database...")
            chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
            chroma_collection = chroma_client.get_collection("afcd_foods")
            count = chroma_collection.count()
            print(f"✅ ChromaDB ready — {count} foods local!")
        except Exception as e:
            print(f"⚠️ ChromaDB failed: {e}")

# ── Vector DB setup ───────────────────────────────
chroma_collection = None
embedding_model = None

def init_vector_db():
    global chroma_collection, embedding_model
    print(f"DEBUG init_vector_db called: "
          f"AVAILABLE={VECTOR_SEARCH_AVAILABLE}, "
          f"USE={USE_VECTOR_SEARCH}")    # ← add this line
    if not VECTOR_SEARCH_AVAILABLE or not USE_VECTOR_SEARCH:
        print("Vector search disabled — using text matching")
        return
    try:
        print("Loading vector database...")
        chroma_client = chromadb.PersistentClient(path="./food_vectors")
        chroma_collection = chroma_client.get_collection("afcd_foods")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        count = chroma_collection.count()
        print(f"✅ Vector DB loaded — {count} foods ready")
    except Exception as e:
        print(f"⚠️ Vector DB failed to load: {e}")
        print("   Falling back to text matching")

# init_vector_db()


# ── Vector search function ────────────────────────
def vector_search_food(food_name, n_results=5):
    """
    Search AFCD using semantic vector similarity
    Returns same format as get_candidates() for compatibility
    """
    if not chroma_collection or not embedding_model:
        return None

    try:
        # Generate embedding for the query
        embedding = embedding_model.encode([food_name]).tolist()

        # Search ChromaDB
        results = chroma_collection.query(
            query_embeddings=embedding,
            n_results=n_results
        )

        if not results or not results['ids'][0]:
            return None

        # Format results same as get_candidates()
        candidates = []
        for i, food_key in enumerate(results['ids'][0]):
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]
            candidates.append({
                'food_key': food_key,
                'food_name': metadata['food_name'],
                'energy_kcal': metadata['energy_kcal'],
                'distance': distance,
                # Convert distance to similarity score
                # distance 0 = perfect match, 1 = completely different
                'similarity': round(1 - distance, 3)
            })

        return candidates

    except Exception as e:
        request_log(f"Vector search error: {e}")
        return None
    
def search_food_vector(food_name, cooking_method="", n_results=5):
    """
    Single search function — automatically uses Qdrant or ChromaDB
    based on USE_QDRANT flag. Returns same format either way.
    """
    if not embedding_model:
        return None

    # Build rich query
    query = f"{cooking_method} {food_name}".strip() \
            if cooking_method and cooking_method != "not applicable" \
            else food_name

    # Generate embedding — same for both backends
    embedding = embedding_model.encode([query])[0].tolist()

    try:
        if USE_QDRANT and qdrant_client_instance:
            # ── Search Qdrant Cloud ───────────────
            results = qdrant_client_instance.query_points(
                collection_name=QDRANT_COLLECTION,
                query=embedding,
                limit=n_results,
                with_payload=True,
                score_threshold=0.3
            ).points

            matches = []
            for hit in results:
                p = hit.payload
                matches.append({
                    'food_key':      p.get('food_key'),
                    'food_name':     p.get('food_name'),
                    'similarity':    round(hit.score, 3),
                    'energy_kcal':   p.get('energy_kcal', 0),
                    'protein':       p.get('protein', 0),
                    'fat':           p.get('fat', 0),
                    'carbohydrates': p.get('carbohydrates', 0),
                    'fibre':         p.get('fibre', 0),
                    'sugars':        p.get('sugars', 0),
                    'sodium':        p.get('sodium', 0),
                    'calcium':       p.get('calcium', 0),
                    'iron':          p.get('iron', 0),
                    'magnesium':     p.get('magnesium', 0),
                    'potassium':     p.get('potassium', 0),
                    'zinc':          p.get('zinc', 0),
                    'vitamin_a':     p.get('vitamin_a', 0),
                    'vitamin_c':     p.get('vitamin_c', 0),
                    'vitamin_d':     p.get('vitamin_d', 0),
                    'vitamin_e':     p.get('vitamin_e', 0),
                    'cholesterol':   p.get('cholesterol', 0),
                })
            return matches if matches else None

        elif not USE_QDRANT and chroma_collection:
            # ── Search ChromaDB Local ─────────────
            results = chroma_collection.query(
                query_embeddings=[embedding],
                n_results=n_results
            )
            if not results or not results['ids'][0]:
                return None

            matches = []
            for i, food_key in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                similarity = round(1 - distance, 3)

                # ChromaDB has metadata but not full nutrition
                # Fall back to SQLite for nutrition data
                nutrition = get_nutrition_by_key(food_key) or {}

                matches.append({
                    'food_key':      food_key,
                    'food_name':     metadata.get('food_name', ''),
                    'similarity':    similarity,
                    'energy_kcal':   nutrition.get('energy_kcal', 0),
                    'protein':       nutrition.get('protein', 0),
                    'fat':           nutrition.get('fat', 0),
                    'carbohydrates': nutrition.get('carbohydrates', 0),
                    'fibre':         nutrition.get('fibre', 0),
                    'sugars':        nutrition.get('sugars', 0),
                    'sodium':        nutrition.get('sodium', 0),
                    'calcium':       nutrition.get('calcium', 0),
                    'iron':          nutrition.get('iron', 0),
                    'magnesium':     nutrition.get('magnesium', 0),
                    'potassium':     nutrition.get('potassium', 0),
                    'zinc':          nutrition.get('zinc', 0),
                    'vitamin_a':     nutrition.get('vitamin_a', 0),
                    'vitamin_c':     nutrition.get('vitamin_c', 0),
                    'vitamin_d':     nutrition.get('vitamin_d', 0),
                    'vitamin_e':     nutrition.get('vitamin_e', 0),
                    'cholesterol':   nutrition.get('cholesterol', 0),
                })
            return matches if matches else None

    except Exception as e:
        request_log(f"Vector search error: {e}")
        return None

    return None


app = Flask(__name__)


# Temporary debug endpoint to inspect which `analyze_with_claude_image`
# implementation is currently available to the running server.
@app.route('/_debug_claude_source')
def _debug_claude_source():
    try:
        src = inspect.getsource(analyze_with_claude_image)
    except Exception as e:
        src = f'Could not get source: {e}'
    return jsonify({
        'app_file': __file__,
        'analyze_with_claude_image_source': src
    })


def request_log(msg):
    try:
        if not hasattr(g, 'request_log'):
            g.request_log = []
        g.request_log.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
    except Exception:
        print("LOG:", msg)

# ─── Query helpers ────────────────────────────────────
def normalize_text(text):
    if not text:
        return ''
    cleaned = re.sub(r'[^a-z0-9 ]+', ' ', text.lower())
    return re.sub(r'\s+', ' ', cleaned).strip()


def build_word_query(words):
    params = [f'%{word}%' for word in words]
    clause = ' AND '.join(['LOWER(food_name) LIKE ?'] * len(words))
    return clause, params


def resolve_provider(request_data):
    provider = request_data.get('provider', AI_PROVIDER)
    provider = provider.lower() if isinstance(provider, str) else AI_PROVIDER
    return provider if provider in SUPPORTED_PROVIDERS else AI_PROVIDER


def score_text_match(query, target):
    qwords = normalize_text(query).split()
    twords = normalize_text(target).split()
    if not qwords or not twords:
        return 0
    common = sum(1 for word in qwords if word in twords)
    return common / len(qwords)


def get_db():
    conn = sqlite3.connect('food_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def search_food(food_name):
    try:
        conn = get_db()
        cursor = conn.cursor()
        normalized = normalize_text(food_name)
        words = normalized.split()

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

        cursor.execute(query, (f'%{normalized}%',))
        result = cursor.fetchone()

        if not result and len(words) > 1:
            clause, params = build_word_query(words)
            cursor.execute(f"""
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
                WHERE {clause}
                ORDER BY LENGTH(food_name) ASC
                LIMIT 1
            """, params)
            result = cursor.fetchone()

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
            """, (f'%{normalized}%',))
            result = cursor.fetchone()

        conn.close()
        return dict(result) if result else None

    except Exception as e:
        print(f"DB search error for '{food_name}': {e}")
        return None

# ─── Gemini AI ───────────────────────────────────────
def analyze_with_gemini(image_base64, mime_type="image/jpeg"):
    if not GEMINI_API_KEY:
        return {"error": "Missing GEMINI_API_KEY environment variable. Add it to .env or set it in your shell."}
    request_log(f"Calling Gemini with image size={len(image_base64)} bytes, mime={mime_type}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    # payload = {
    #     "contents": [{
    #         "parts": [
    #             {"inline_data": {"mime_type": mime_type, "data": image_base64}},
    #             {"text": """Analyze this food image. List each food item you see.
    #                 Respond ONLY in this exact JSON format, no other text:
    #                 {
    #                     "foods": [
    #                         {"name": "food name", "estimated_grams": 100}
    #                     ],
    #                     "meal_description": "brief description"
    #                 }"""}
    #         ]
    #     }]
    # }

    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_base64
                    }
                },
                {"text": """You are an expert food analyst and nutritionist.
            Analyse this food plate image carefully.

            RULES:
            1. Identify every distinct food item visible on the plate
            2. Be specific - use the most precise food name possible
            3. For cooking method: use 'raw', 'grilled', 'fried', 'boiled', 
            'steamed', 'baked', 'roasted', 'sauteed'
            4. For leafy greens: identify the specific type if visible 
            (spinach/rocket/cos lettuce/baby spinach/mixed leaves)
            - if truly cannot identify, use 'mixed leafy salad greens'
            5. For sauces/dressings: identify as specifically as possible
            (mayonnaise/tomato sauce/chilli sauce/yoghurt dressing)
            6. Estimate weight in grams based on visual portion size
            7. Confidence: 'high' if clearly visible, 
                        'medium' if partially visible or overlapping,
                        'low' if guessing based on context
            8. Consider ALL cuisines - Australian, Indian, Asian, 
            Mediterranean, Middle Eastern, etc.

            Respond ONLY in this exact JSON format, no other text:
            {
                "foods": [
                    {
                        "name": "specific food name",
                        "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|sauteed|not applicable",
                        "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
                        "estimated_grams": 100,
                        "confidence": "high|medium|low",
                        "visual_notes": "brief note on what you actually see"
                    }
                ],
                "meal_description": "brief description",
                "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
                "plate_coverage": "full|partial|half eaten"
            }"""
                        }
                    ]
                }]
            }
    

    response = requests.post(url, json=payload)
    request_log(f"Gemini HTTP status: {response.status_code}")
    if response.status_code != 200:
        return {"error": f"Gemini API error {response.status_code}: {response.text}"}

    try:
        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        request_log(f"Gemini returned response length={len(response.text)}")
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        request_log(f"Failed to parse Gemini response: {e}")
        return {"error": f"Failed to parse Gemini response: {e}. Response text: {response.text}"}

def analyze_with_claude_text(voice_text):
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY environment variable."}

    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",      # ← required header
        "Content-Type": "application/json"
    }

    payload = {
        "model": "claude-haiku-4-5",            # ← correct model name
        "max_tokens": 1000,
        "messages": [                            # ← messages array, not prompt
            {
                "role": "user",
                "content": f"""Extract food items from this text: \"{voice_text}\"
Respond ONLY in this exact JSON format, no other text:
{{
    "foods": [
        {{
            "name": "specific food name",
            "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|sauteed|not applicable",
            "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
            "estimated_grams": 100,
            "confidence": "high|medium|low",
            "visual_notes": "extracted from voice description"
        }}
    ],
    "meal_description": "brief description",
    "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
    "plate_coverage": "full"
}}"""
            }
        ]
    }

    response = requests.post(url, headers=headers, json=payload)
    request_log(f"Claude text HTTP status: {response.status_code}")

    if response.status_code != 200:
        return {"error": f"Claude API error {response.status_code}: {response.text}"}

    try:
        result = response.json()
        text = result["content"][0]["text"].strip()  # ← correct response parsing
        request_log(f"Claude text returned length={len(text)}")

        # Clean markdown if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        return json.loads(text.strip())
    except Exception as e:
        request_log(f"Failed to parse Claude text response: {e}")
        return {"error": f"Failed to parse Claude response: {e}"}


def analyze_with_claude_image(image_base64, mime_type="image/jpeg"):
    if not CLAUDE_API_KEY:
        return {"error": "Missing CLAUDE_API_KEY environment variable."}

    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "claude-haiku-4-5",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",           # ← image block first
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_base64
                        }
                    },
                    {
                        "type": "text",            # ← text block second
                        "text": """You are an expert food analyst and nutritionist.
    Analyse this food plate image carefully.

    RULES:
    1. Identify every distinct food item visible on the plate
    2. Be specific - use the most precise food name possible
    3. For cooking method: use 'raw', 'grilled', 'fried', 'boiled',
    'steamed', 'baked', 'roasted', 'sauteed'
    4. For leafy greens: identify the specific type if visible
    (spinach/rocket/cos lettuce/baby spinach/mixed leaves)
    - if truly cannot identify, use 'mixed leafy salad greens'
    5. For sauces/dressings: identify as specifically as possible
    (mayonnaise/tomato sauce/chilli sauce/yoghurt dressing)
    6. Estimate weight in grams based on visual portion size
    7. Confidence: 'high' if clearly visible,
                'medium' if partially visible or overlapping,
                'low' if guessing based on context
    8. Consider ALL cuisines - Australian, Indian, Asian,
    Mediterranean, Middle Eastern, etc.
    9. CRITICAL - Use ingredient names NOT dish names:
        - Say 'avocado, raw' NOT 'guacamole'
        - Say 'tomato salsa' NOT 'pico de gallo'  
        - Say 'chickpea curry' NOT 'chole'
        - Say 'fried bread' NOT 'puri'
        This helps match to our nutrition database

    10. For bread/rolls be specific but simple:
        - 'white bread roll' not 'submarine sandwich roll'
        - 'sourdough bread' not 'artisan sourdough loaf'
        - 'naan bread' not 'traditional tandoor naan'
    11. Distinguish raw vs cooked carefully:
        - White crisp onion rings = raw
        - Soft brown translucent onion = cooked/caramelized
        - Bright red tomato = fresh/raw
        - Dark chewy tomato = sundried
    12. Only list food items you can clearly see.
        Do NOT guess hidden ingredients inside sandwiches
        unless clearly visible at the edges.


    Respond ONLY in this exact JSON format, no other text:
    {
        "foods": [
            {
                "name": "specific food name",
                "cooking_method": "raw|grilled|fried|boiled|steamed|baked|roasted|sauteed|not applicable",
                "category": "protein|grain|vegetable|fruit|dairy|sauce|condiment|beverage",
                "estimated_grams": 100,
                "confidence": "high|medium|low",
                "visual_notes": "brief note on what you actually see"
            }
        ],
        "meal_description": "brief description",
        "cuisine_type": "Indian|Australian|Asian|Mediterranean|Western|Mixed|Unknown",
        "plate_coverage": "full|partial|half eaten"
    }"""
                        }
                    ]
                }
            ]
        }

    response = requests.post(url, headers=headers, json=payload)
    request_log(f"Claude image HTTP status: {response.status_code}")

    if response.status_code != 200:
        return {"error": f"Claude API error {response.status_code}: {response.text}"}

    try:
        result = response.json()
        text = result["content"][0]["text"].strip()
        request_log(f"Claude image returned length={len(text)}")

        # Clean markdown if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        return json.loads(text.strip())
    except Exception as e:
        request_log(f"Failed to parse Claude image response: {e}")
        return {"error": f"Failed to parse Claude response: {e}"}
    


def analyze_with_openai_image(image_base64, mime_type="image/jpeg"):
    if not OPENAI_API_KEY:
        return {"error": "Missing OPENAI_API_KEY environment variable. Add it to .env or set it in your shell."}

    url = "https://api.openai.com/v1/responses"
    prompt_text = (
        "Extract food items from the attached image and respond ONLY in this exact JSON format, no extra text:\n"
        "{\n  \"foods\": [ {\"name\": \"food name\", \"estimated_grams\": 100} ],\n  \"meal_description\": \"brief description\"\n}"
    )

    # Many OpenAI Responses endpoints do not accept an `image_base64` parameter directly.
    # Embed the image as a data URL in the text prompt so the model receives the image content.
    data_url = f"data:{mime_type};base64,{image_base64}"
    combined_prompt = prompt_text + "\n\nImage (base64): " + data_url

    payload = {
        "model": OPENAI_VISION_MODEL,
        "temperature": 0,
        "max_output_tokens": 800,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": combined_prompt}
                ]
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    request_log(f"Calling OpenAI model={OPENAI_VISION_MODEL}, prompt_len={len(combined_prompt)}")
    # Estimate tokens: prefer tiktoken if available for model-specific accuracy
    if tiktoken:
        try:
            enc = tiktoken.encoding_for_model(OPENAI_VISION_MODEL)
            est_tokens = len(enc.encode(combined_prompt))
        except Exception:
            est_tokens = math.ceil(len(combined_prompt) / 4)
    else:
        est_tokens = math.ceil(len(combined_prompt) / 4)
    request_log(f"OpenAI estimated tokens (server): {est_tokens}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    except Exception as e:
        request_log(f"OpenAI request failed: {e}")
        return {"error": f"OpenAI request failed: {e}"}

    request_log(f"OpenAI returned status={response.status_code}")
    if response.status_code != 200:
        return {"error": f"OpenAI API error {response.status_code}: {response.text}"}

    try:
        result = response.json()
    except Exception as e:
        request_log(f"Failed to decode OpenAI response JSON: {e}")
        return {"error": f"Failed to decode OpenAI response JSON: {e}. Raw: {response.text}"}

    # Try to extract text output from common fields
    text = None
    if isinstance(result.get('output'), list):
        for out in result.get('output'):
            for c in out.get('content', []):
                if c.get('type') in ('output_text', 'text'):
                    text = c.get('text') or c.get('content')
                    if text:
                        break
            if text:
                break

    if not text:
        text = result.get('output_text') or (result.get('choices') and result['choices'][0].get('message', {}).get('content', ''))

    if not text:
        request_log("OpenAI response did not contain parsable text")
        return {"error": f"OpenAI response did not contain parsable text. Raw: {json.dumps(result)[:500]}"}

    # remove code fences if present
    if "```" in text:
        parts = text.split('```')
        if len(parts) >= 2:
            candidate = parts[1]
            if candidate.strip().startswith('json'):
                candidate = candidate.strip()[4:]
            text = candidate

    request_log(f"Extracted text length after cleaning: {len(text)}")

    try:
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed to parse OpenAI response as JSON: {e}. Response text: {text}"}


def analyze_with_model(image_base64, mime_type="image/jpeg", provider="gemini"):
    provider = provider.lower()
    if provider == "claude":
        return analyze_with_claude_image(image_base64, mime_type)
    if provider == "openai":
        return analyze_with_openai_image(image_base64, mime_type)
    return analyze_with_gemini(image_base64, mime_type)


def analyze_text_model(voice_text, provider="gemini"):
    provider = provider.lower()
    if provider == "claude":
        return analyze_with_claude_text(voice_text)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [{
                "text": f"""Extract food items from this text: \"{voice_text}\"\n                    Respond ONLY in this exact JSON format:\n                    {{\n                        \"foods\": [\n                            {{\"name\": \"food name\", \"estimated_grams\": 100}}\n                        ],\n                        \"meal_description\": \"brief description\"\n                    }}"""
            }]
        }]
    }
    response  = requests.post(url, json=payload)
    if response.status_code != 200:
        return {"error": f"Gemini API error {response.status_code}: {response.text}"}

    try:
        result = response.json()
        text   = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {"error": f"Failed to parse Gemini response: {e}. Response text: {response.text}"}

# ─── Nutrition calculator ─────────────────────────────
def calculate_row_nutrition(item):
    grams = item.get('grams', 0) or 0
    per100 = item.get('per100', {}) or {}
    def calc(key):
        return round((per100.get(key, 0) or 0) * grams / 100, 2)

    return {
        'name': item.get('name', ''),
        'grams': grams,
        'matched': item.get('matched', 'Not found'),
        'found_in_db': item.get('found_in_db', False),
        'calories': calc('energy_kcal'),
        'protein': calc('protein'),
        'fat': calc('fat'),
        'carbohydrates': calc('carbohydrates'),
        'fibre': calc('fibre'),
        'sugars': calc('sugars'),
        'sodium': calc('sodium'),
        'calcium': calc('calcium'),
        'iron': calc('iron'),
        'magnesium': calc('magnesium'),
        'potassium': calc('potassium'),
        'zinc': calc('zinc'),
        'vitamin_a': calc('vitamin_a'),
        'vitamin_c': calc('vitamin_c'),
        'vitamin_d': calc('vitamin_d'),
        'vitamin_e': calc('vitamin_e'),
        'cholesterol': calc('cholesterol'),
        'per100': per100,
    }


def calculate_nutrition(ai_result):
    foods_with_nutrition = []
    total_calories = 0

    for food in ai_result.get('foods', []):
        grams = food.get('estimated_grams', 0)
        food_name = food.get('name', '')
        confidence = food.get('confidence', 'high')
        category = food.get('category', '')
        cooking_method = food.get('cooking_method', '')

        request_log(f"Looking up '{food_name}' ({grams}g) "
                   f"[confidence={confidence}]")

        best_key = None
        matched_name = 'Not found'
        n = None
        match_method = 'none'

        # ── Vector search path ────────────────────────────
        if (USE_QDRANT and QDRANT_AVAILABLE) or \
        (not USE_QDRANT and CHROMADB_AVAILABLE):

            vector_results = search_food_vector(
                food_name,
                cooking_method,
                n_results=5
            )

            if vector_results:
                best = vector_results[0]
                similarity = best['similarity']
                backend = "Qdrant" if USE_QDRANT else "ChromaDB"
                request_log(f"{backend} match: '{best['food_name']}' "
                        f"similarity={similarity}")

                if similarity >= 0.65:
                    n = best
                    match_method = f'{backend.lower()} ({similarity})'
                elif similarity >= 0.45 and confidence != 'low':
                    n = best
                    match_method = f'{backend.lower()}-medium ({similarity})'
                    request_log(f"⚠️ Medium similarity for '{food_name}'")
                else:
                    request_log(f"Similarity too low ({similarity}) "
                            f"for '{food_name}'")
                    
        # # ── Vector search path ────────────────────
        # if USE_VECTOR_SEARCH and VECTOR_SEARCH_AVAILABLE:
        #     # Build richer query using all Claude's context
        #     search_query = food_name
        #     if cooking_method and cooking_method != 'not applicable':
        #         search_query = f"{cooking_method} {food_name}"

        #     vector_results = vector_search_food(search_query, n_results=5)

        #     if vector_results:
        #         best = vector_results[0]
        #         similarity = best['similarity']
        #         request_log(f"Vector match: '{best['food_name']}' "
        #                    f"similarity={similarity}")

        #         # High confidence threshold
        #         if similarity >= 0.65:
        #             best_key = best['food_key']
        #             match_method = f'vector ({similarity})'
        #         elif similarity >= 0.45 and confidence != 'low':
        #             # Medium confidence — use but flag it
        #             best_key = best['food_key']
        #             match_method = f'vector-medium ({similarity})'
        #             request_log(f"⚠️ Medium similarity match for "
        #                        f"'{food_name}'")
        #         else:
        #             request_log(f"Vector similarity too low ({similarity})"
        #                        f" for '{food_name}' — no match")

        # ── Text search fallback ──────────────────
        else:
            candidates = get_candidates(food_name)
            request_log(f"Found {len(candidates)} candidates")

            best_key = find_best_candidate_key(food_name, candidates)

            if not best_key:
                if len(candidates) == 1:
                    best_key = candidates[0]['food_key']
                    request_log(f"Single candidate auto-matched")
                elif len(candidates) > 1:
                    request_log(f"Candidates ambiguous, asking AI")
                    best_key = ask_gemini_to_match(
                        food_name, grams, candidates)
                else:
                    request_log(f"No candidates found")

            match_method = 'text'

        # ── Get nutrition by key ──────────────────
        if best_key:
            n = get_nutrition_by_key(best_key)

        # ── Final fallback ────────────────────────
        if not n:
            request_log(f"Falling back to fuzzy search for '{food_name}'")
            n = search_food(food_name)

        def calc(key):
            return round((n.get(key, 0) or 0) * grams / 100, 2) if n else 0

        matched_name = n['food_name'] if n else 'Not found'
        request_log(f"Final match → {matched_name} [{match_method}]")

        entry = {
            "name": food_name,
            "matched": matched_name,
            "grams": grams,
            "found_in_db": n is not None,
            "confidence": confidence,
            "cooking_method": cooking_method,
            "category": category,
            "warning": "Low confidence — please verify" \
                       if confidence == 'low' else None,
            "calories": calc('energy_kcal'),
            "protein": calc('protein'),
            "fat": calc('fat'),
            "carbs": calc('carbohydrates'),
            "fibre": calc('fibre'),
            "sugars": calc('sugars'),
            "sodium": calc('sodium'),
            "calcium": calc('calcium'),
            "iron": calc('iron'),
            "magnesium": calc('magnesium'),
            "potassium": calc('potassium'),
            "zinc": calc('zinc'),
            "vitamin_a": calc('vitamin_a'),
            "vitamin_c": calc('vitamin_c'),
            "vitamin_d": calc('vitamin_d'),
            "vitamin_e": calc('vitamin_e'),
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
        g.request_log = []
        request_log("Received /analyze request")
        image_base64  = data.get('image')
        mime_type     = data.get('mime_type', 'image/jpeg')
        provider      = resolve_provider(data)
        image_w = data.get('image_width')
        image_h = data.get('image_height')
        client_tokens = data.get('client_estimated_tokens')

        request_log(f"Provider resolved: {provider}")
        request_log(f"Incoming image size (base64 chars): {len(image_base64) if image_base64 else 0}")
        request_log(f"Incoming image pixels: {image_w}x{image_h}")
        request_log(f"Client estimated tokens: {client_tokens}")

        if Image is None:
            request_log("Pillow (PIL) not installed: server-side image resize disabled. Install Pillow to enable.")
        if tiktoken is None:
            request_log("tiktoken not installed: server-side token counts will use a heuristic.")

        # Server-side resize/compress fallback to limit tokens and bandwidth
        resized_base64 = image_base64
        resized_w, resized_h = image_w, image_h
        if image_base64 and Image is not None:
            try:
                img_data = b64decode(image_base64)
                img = Image.open(BytesIO(img_data))
                orig_w, orig_h = img.size
                max_w, max_h = 1200, 900
                ratio = min(max_w / orig_w, max_h / orig_h, 1)
                if ratio < 1:
                    tw = max(1, int(orig_w * ratio))
                    th = max(1, int(orig_h * ratio))
                    img = img.convert('RGB')
                    img = img.resize((tw, th), Image.LANCZOS)
                    out = BytesIO()
                    img.save(out, format='JPEG', quality=80)
                    out_b = out.getvalue()
                    resized_base64 = b64encode(out_b).decode('ascii')
                    resized_w, resized_h = tw, th
                    request_log(f"Server resized image {orig_w}x{orig_h} -> {tw}x{th}, bytes={len(out_b)}")
                else:
                    request_log(f"Server no-resize needed for image {orig_w}x{orig_h}")
            except Exception as e:
                request_log(f"Server-side resize failed: {e}")

        # replace image with resized version for downstream calls
        image_base64 = resized_base64
        image_w, image_h = resized_w, resized_h
        request_log(f"Image used for analysis pixels: {image_w}x{image_h}")

        ai_result = analyze_with_model(image_base64, mime_type, provider)
        if isinstance(ai_result, dict) and ai_result.get("error"):
            return jsonify({"error": ai_result["error"]}), 500

        foods, total_calories = calculate_nutrition(ai_result)
        result = {
            "meal_description": ai_result['meal_description'],
            "foods":            foods,
            "total_calories":   total_calories,
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_meal_log(result)
        # Include request log in response for UI debugging
        result["debug_log"] = g.request_log
        return jsonify(result)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/analyze-voice', methods=['POST'])
def analyze_voice():
    try:
        data       = request.get_json()
        g.request_log = []
        request_log("Received /analyze-voice request")
        voice_text = data.get('text', '')
        provider   = resolve_provider(data)

        request_log(f"Provider resolved: {provider}")
        request_log(f"Voice text length: {len(voice_text)}")

        ai_result = analyze_text_model(voice_text, provider)
        if isinstance(ai_result, dict) and ai_result.get("error"):
            return jsonify({"error": ai_result["error"]}), 500

        foods, total_calories = calculate_nutrition(ai_result)
        result = {
            "meal_description": ai_result['meal_description'],
            "foods":            foods,
            "total_calories":   total_calories,
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_meal_log(result)
        result["debug_log"] = g.request_log
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
    """Get candidate matches from the database using phrase, all-words, and individual words."""
    conn = get_db()
    cursor = conn.cursor()

    normalized = normalize_text(food_name)
    words = [w for w in normalized.split() if w]
    seen = set()
    candidates = []

    def add_rows(rows):
        for c in rows:
            if c['food_key'] not in seen:
                seen.add(c['food_key'])
                candidates.append(c)

    # Exact phrase match first
    cursor.execute("""
        SELECT food_key, food_name, energy_kcal
        FROM foods_afcd
        WHERE LOWER(food_name) LIKE ?
        ORDER BY LENGTH(food_name) ASC
        LIMIT 20
    """, (f'%{normalized}%',))
    add_rows(cursor.fetchall())

    # Match all query words in any order
    if len(words) > 1:
        clause, params = build_word_query(words)
        cursor.execute(f"""
            SELECT food_key, food_name, energy_kcal
            FROM foods_afcd
            WHERE {clause}
            ORDER BY LENGTH(food_name) ASC
            LIMIT 30
        """, params)
        add_rows(cursor.fetchall())

    # Also include results for each individual term
    for word in words:
        if len(word) > 2:
            cursor.execute("""
                SELECT food_key, food_name, energy_kcal
                FROM foods_afcd
                WHERE LOWER(food_name) LIKE ?
                ORDER BY LENGTH(food_name) ASC
                LIMIT 20
            """, (f'%{word}%',))
            add_rows(cursor.fetchall())

    conn.close()
    return [dict(c) for c in candidates[:40]]


# def find_best_candidate_key(food_name, candidates):
#     normalized = normalize_text(food_name)
#     words = normalized.split()

#     for c in candidates:
#         cand_norm = normalize_text(c['food_name'])
#         if cand_norm == normalized:
#             return c['food_key']

#     if words:
#         for c in candidates:
#             cand_norm = normalize_text(c['food_name'])
#             if all(word in cand_norm.split() for word in words):
#                 return c['food_key']

#     scored = [(score_text_match(food_name, c['food_name']), c) for c in candidates]
#     scored.sort(key=lambda item: item[0], reverse=True)
#     if scored and scored[0][0] >= 0.65:
#         return scored[0][1]['food_key']

#     return None

def find_best_candidate_key(food_name, candidates):
    normalized = normalize_text(food_name)
    words = normalized.split()

    # Exact match first
    for c in candidates:
        cand_norm = normalize_text(c['food_name'])
        if cand_norm == normalized:
            return c['food_key']

    # All words match
    if words:
        for c in candidates:
            cand_norm = normalize_text(c['food_name'])
            if all(word in cand_norm.split() for word in words):
                return c['food_key']

    # Score with processing term penalty
    PROCESSING_TERMS = ['sundried', 'dried', 'powdered',
                        'oil', 'juice', 'paste', 'canned',
                        'pickled', 'frozen', 'dehydrated']

    scored = []
    for c in candidates:
        score = score_text_match(food_name, c['food_name'])
        cand_norm = normalize_text(c['food_name'])
        for term in PROCESSING_TERMS:
            if term in cand_norm and term not in normalized:
                score -= 0.3
        scored.append((score, c))

    scored.sort(key=lambda item: item[0], reverse=True)

    if scored and scored[0][0] >= 0.5:
        return scored[0][1]['food_key']

    return None

def ask_gemini_to_match(food_name, grams, candidates):
    """Ask Gemini to pick the best matching food from candidates"""
    if not candidates:
        return None

    candidate_list = "\n".join([
        f"- Key: {c['food_key']} | {c['food_name']} | {c['energy_kcal']} kcal/100g"
        for c in candidates[:30]
    ])

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [{
                "text": f"""I have identified \"{food_name}\" ({grams}g) in a food image.
From the Australian Food Composition Database, these are the closest matches:

{candidate_list}

Use the full list of candidates, including any matches for individual words such as \"grilled\" and \"chicken\".
Choose the best food key for the meal item, then respond ONLY with that food key. Example: F001234"""
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

@app.route('/recalculate', methods=['POST'])
def recalculate():
    try:
        data = request.get_json() or {}
        foods = data.get('foods', [])
        if not isinstance(foods, list):
            return jsonify({'error': 'Invalid payload, expected foods array.'}), 400

        recalculated = []
        for item in foods:
            name = str(item.get('name', '') or '').strip()
            try:
                grams = float(item.get('grams', 0) or 0)
            except Exception:
                grams = 0

            per100 = None
            matched_name = 'Not found'
            found_in_db = False
            if name:
                candidates = get_candidates(name)
                best_key = find_best_candidate_key(name, candidates)
                if best_key:
                    per100 = get_nutrition_by_key(best_key)
                    if per100:
                        matched_name = per100.get('food_name', name)
                        found_in_db = True
                if not per100:
                    search_result = search_food(name)
                    if search_result:
                        per100 = search_result
                        matched_name = search_result.get('food_name', name)
                        found_in_db = True

            if not per100:
                per100 = {
                    'food_name': name,
                    'energy_kcal': 0, 'protein': 0, 'fat': 0, 'carbohydrates': 0,
                    'fibre': 0, 'sugars': 0, 'sodium': 0, 'calcium': 0,
                    'iron': 0, 'magnesium': 0, 'potassium': 0, 'zinc': 0,
                    'vitamin_a': 0, 'vitamin_c': 0, 'vitamin_d': 0,
                    'vitamin_e': 0, 'cholesterol': 0
                }

            entry = calculate_row_nutrition({
                'name': name,
                'grams': grams,
                'per100': per100,
                'matched': matched_name,
                'found_in_db': found_in_db
            })
            entry['per100'] = per100
            entry['matched'] = matched_name
            entry['found_in_db'] = found_in_db
            recalculated.append(entry)

        return jsonify({'foods': recalculated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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


# ─── Bottom of app.py ────────────────────────────

if __name__ == '__main__':
    init_vector_search()    # ← make sure NO # at the start!
    app.run(host='0.0.0.0', port=5000, debug=True)