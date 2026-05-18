# Test embedding-based food search
import sqlite3, requests, json, os, math
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_query_embedding(text):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={GEMINI_API_KEY}'
    r = requests.post(url, json={
        'model': 'models/gemini-embedding-2',
        'content': {'parts': [{'text': text.lower()}]}
    })
    if r.status_code == 200:
        return r.json()['embedding']['values']
    print(f"Embedding error: {r.status_code}")
    return None

def cosine_similarity(a, b):
    dot   = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0

def search_by_embedding(food_name, top_k=5):
    query_vec = get_query_embedding(food_name)
    if not query_vec:
        return []

    conn = sqlite3.connect('food_database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT food_key, food_name, energy_kcal, embedding
        FROM foods_afcd
        WHERE embedding IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()

    scored = []
    for row in rows:
        try:
            vec   = json.loads(row['embedding'])
            score = cosine_similarity(query_vec, vec)
            scored.append({
                'food_key':   row['food_key'],
                'food_name':  row['food_name'],
                'energy_kcal': row['energy_kcal'],
                'score':      score
            })
        except:
            continue

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_k]

# Test searches
tests = [
    'banana',
    'fried eggs',
    'grilled tomato',
    'chicken curry',
    'white rice cooked',
    'fish grilled',
    'broccoli steamed',
]

print("🔍 Embedding Search Test\n")
for query in tests:
    print(f"Query: '{query}'")
    results = search_by_embedding(query, top_k=20)
    for r in results:
        print(f"  {r['score']:.3f} | {r['food_name'][:50]} | {r['energy_kcal']} kcal")
    print()