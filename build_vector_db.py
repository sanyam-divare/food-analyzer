# build_vector_db.py
# Run ONCE to load all AFCD foods into ChromaDB
# After this, app.py uses vector search instead of text matching
# Usage: python build_vector_db.py

import sqlite3
import chromadb
from sentence_transformers import SentenceTransformer
import time

DB_FILE = 'food_database.db'
CHROMA_PATH = './food_vectors'
BATCH_SIZE = 100

print("🚀 Starting ChromaDB vector database build...")
print()

# ── Step 1: Load foods from your existing SQLite ──
print("📂 Reading foods from SQLite...")
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT 
        food_key, food_name, energy_kcal,
        protein, fat, carbohydrates, fibre,
        sodium, calcium, iron, magnesium,
        potassium, zinc, vitamin_a, vitamin_c,
        vitamin_d, vitamin_e, cholesterol, sugars
    FROM foods_afcd
    ORDER BY food_key
""")

foods = [dict(row) for row in cursor.fetchall()]
conn.close()

print(f"✅ Loaded {len(foods)} foods from SQLite")
print()

# ── Step 2: Load embedding model ──────────────────
print("🧠 Loading sentence-transformers model...")
print("   (first run downloads ~90MB — subsequent runs are instant)")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("✅ Model loaded!")
print()

# ── Step 3: Setup ChromaDB ────────────────────────
print(f"🗄️  Setting up ChromaDB at: {CHROMA_PATH}")
client = chromadb.PersistentClient(path=CHROMA_PATH)

# Delete existing collection if rebuilding
try:
    client.delete_collection("afcd_foods")
    print("   Cleared existing collection")
except:
    pass

collection = client.create_collection(
    name="afcd_foods",
    metadata={"hnsw:space": "cosine"}
)
print("✅ ChromaDB collection created!")
print()

# ── Step 4: Build rich text for embedding ─────────
def build_embedding_text(food):
    """
    Combine food name + key nutritional context
    This makes vectors much smarter than name alone
    
    Example:
    "Avocado, hass, raw | high fat | low protein | fruit vegetable"
    vs
    "Oil, avocado | very high fat | zero protein | oils fats"
    → These will be far apart in vector space! ✅
    """
    name = food['food_name']
    
    # Add nutritional context hints
    fat = food.get('fat') or 0
    protein = food.get('protein') or 0
    carbs = food.get('carbohydrates') or 0
    energy = food.get('energy_kcal') or 0

    # Nutritional character tags
    tags = []
    if fat > 20:
        tags.append("high fat")
    elif fat > 10:
        tags.append("moderate fat")
    elif fat < 2:
        tags.append("low fat")

    if protein > 20:
        tags.append("high protein")
    elif protein > 10:
        tags.append("moderate protein")
    elif protein < 2:
        tags.append("low protein")

    if carbs > 40:
        tags.append("high carb")
    elif carbs > 15:
        tags.append("moderate carb")
    elif carbs < 5:
        tags.append("low carb")

    if energy > 500:
        tags.append("high calorie")
    elif energy < 50:
        tags.append("low calorie")

    tag_str = " | ".join(tags) if tags else ""
    
    if tag_str:
        return f"{name} | {tag_str}"
    return name

# ── Step 5: Generate embeddings + load to ChromaDB ─
print(f"⚙️  Generating embeddings for {len(foods)} foods...")
print(f"   Processing in batches of {BATCH_SIZE}...")
print()

start_time = time.time()
total_loaded = 0

for i in range(0, len(foods), BATCH_SIZE):
    batch = foods[i:i + BATCH_SIZE]
    
    # Build text for embedding
    texts = [build_embedding_text(food) for food in batch]
    ids = [food['food_key'] for food in batch]
    
    # Build metadata (nutrition per 100g)
    metadatas = []
    for food in batch:
        metadatas.append({
            "food_name": food['food_name'],
            "energy_kcal": float(food.get('energy_kcal') or 0),
            "protein": float(food.get('protein') or 0),
            "fat": float(food.get('fat') or 0),
            "carbohydrates": float(food.get('carbohydrates') or 0),
            "fibre": float(food.get('fibre') or 0),
            "sodium": float(food.get('sodium') or 0),
            "calcium": float(food.get('calcium') or 0),
            "iron": float(food.get('iron') or 0),
            "magnesium": float(food.get('magnesium') or 0),
            "potassium": float(food.get('potassium') or 0),
            "zinc": float(food.get('zinc') or 0),
            "vitamin_a": float(food.get('vitamin_a') or 0),
            "vitamin_c": float(food.get('vitamin_c') or 0),
            "vitamin_d": float(food.get('vitamin_d') or 0),
            "vitamin_e": float(food.get('vitamin_e') or 0),
            "cholesterol": float(food.get('cholesterol') or 0),
            "sugars": float(food.get('sugars') or 0),
        })
    
    # Generate embeddings for this batch
    embeddings = model.encode(texts).tolist()
    
    # Add to ChromaDB
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )
    
    total_loaded += len(batch)
    elapsed = time.time() - start_time
    print(f"   ✅ {total_loaded}/{len(foods)} foods loaded "
          f"({elapsed:.1f}s elapsed)")

print()
total_time = time.time() - start_time
print(f"🎉 Done! {total_loaded} foods loaded in {total_time:.1f} seconds")
print()

# ── Step 6: Test it! ──────────────────────────────
print("🔍 Testing vector search...")
print()

test_queries = [
    "avocado raw chunks",
    "white bread roll",
    "grilled chicken breast",
    "cherry tomatoes fresh",
    "mixed salad greens",
    "paneer cubes grilled",
    "puri fried bread indian",
    "salmon fillet grilled",
]

for query in test_queries:
    results = collection.query(
        query_texts=[query],
        n_results=3
    )
    
    top_name = results['metadatas'][0][0]['food_name']
    top_distance = results['distances'][0][0]
    confidence = "HIGH" if top_distance < 0.3 else \
                 "MEDIUM" if top_distance < 0.5 else "LOW"
    
    print(f"Query: '{query}'")
    print(f"  → {top_name}")
    print(f"     Distance: {top_distance:.3f} | Confidence: {confidence}")
    print()

print("✅ Vector database is ready!")
print()
print("Next steps:")
print("  1. Add USE_VECTOR_SEARCH=true to your .env file")
print("  2. Restart your Flask app: python app.py")
print("  3. Test with a food image!")