import os
import sqlite3
import time
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Load environment configs
load_dotenv(override=True)

COLLECTION_NAME = "food_analyzer"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 produces 384-dimensional vectors
BATCH_SIZE = 100     # process 100 foods at a time

# 1. Initialize Clients
print("🔗 Connecting to Services...")

# Local embedding model — no API, no rate limits, no cost!
print("🧠 Loading sentence-transformers model...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
print("✅ Embedding model ready!")

qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
    prefer_grpc=False
)
print("✅ Qdrant connected!")

# 2. Setup Qdrant Collection
# Delete existing collection if wrong dimensions
if qdrant_client.collection_exists(COLLECTION_NAME):
    existing = qdrant_client.get_collection(COLLECTION_NAME)
    existing_dim = existing.config.params.vectors.size
    if existing_dim != EMBEDDING_DIM:
        print(f"⚠️  Existing collection has {existing_dim} dims, need {EMBEDDING_DIM}")
        print(f"🗑️  Deleting old collection...")
        qdrant_client.delete_collection(COLLECTION_NAME)
        print(f"✅ Old collection deleted!")

if not qdrant_client.collection_exists(COLLECTION_NAME):
    print(f"📦 Creating fresh collection: '{COLLECTION_NAME}'...")
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=EMBEDDING_DIM,
            distance=Distance.COSINE
        )
    )
    print(f"✅ Collection created with {EMBEDDING_DIM} dimensions!")


def get_embeddings_batch(texts):
    """
    Generate embeddings locally using sentence-transformers.
    No API calls, no rate limits, no cost!
    """
    try:
        embeddings = embedding_model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings.tolist()
    except Exception as e:
        print(f"❌ Failed to generate embeddings: {e}")
        return None


def build_embedding_text(food_name):
    """
    Build richer text for embedding than just the food name.
    This improves semantic matching quality.
    Example: "Avocado, hass, raw" → better vectors than just "Avocado"
    """
    return food_name  # Start simple, can enrich later


def migrate_data():
    """
    Streams data from SQLite and upserts into Qdrant Cloud.
    Uses local sentence-transformers — no rate limits!
    """
    # Connect to SQLite
    conn = sqlite3.connect("food_database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get total count for progress reporting
    cursor.execute("SELECT COUNT(*) as total FROM foods_afcd")
    total_foods = cursor.fetchone()["total"]
    print(f"\n📊 Total foods to migrate: {total_foods}")

    # Fetch all foods
    cursor.execute("""
        SELECT 
            id, food_key, food_name,
            energy_kcal, protein, fat, 
            carbohydrates, fibre, sodium,
            calcium, iron, magnesium,
            potassium, zinc, vitamin_c,
            vitamin_a, vitamin_d, vitamin_e,
            cholesterol, sugars
        FROM foods_afcd
        ORDER BY id ASC
    """)

    total_migrated = 0
    batch_num = 0
    start_time = time.time()

    print("🚀 Beginning Migration...")
    print()

    while True:
        rows = cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break

        batch_num += 1

        # Build texts for embedding
        texts = [build_embedding_text(row["food_name"]) for row in rows]

        # Generate embeddings locally — instant, no rate limits!
        embeddings = get_embeddings_batch(texts)

        if not embeddings:
            print(f"⚠️  Batch {batch_num} failed — skipping")
            continue

        # Build Qdrant points with full nutrition payload
        points = []
        for i, row in enumerate(rows):
            points.append(
                PointStruct(
                    id=int(row["id"]),
                    vector=embeddings[i],
                    payload={
                        # Identity
                        "food_key":      row["food_key"],
                        "food_name":     row["food_name"],
                        # Macros per 100g
                        "energy_kcal":   float(row["energy_kcal"] or 0),
                        "protein":       float(row["protein"] or 0),
                        "fat":           float(row["fat"] or 0),
                        "carbohydrates": float(row["carbohydrates"] or 0),
                        "fibre":         float(row["fibre"] or 0),
                        "sugars":        float(row["sugars"] or 0),
                        # Micros per 100g
                        "sodium":        float(row["sodium"] or 0),
                        "calcium":       float(row["calcium"] or 0),
                        "iron":          float(row["iron"] or 0),
                        "magnesium":     float(row["magnesium"] or 0),
                        "potassium":     float(row["potassium"] or 0),
                        "zinc":          float(row["zinc"] or 0),
                        "vitamin_a":     float(row["vitamin_a"] or 0),
                        "vitamin_c":     float(row["vitamin_c"] or 0),
                        "vitamin_d":     float(row["vitamin_d"] or 0),
                        "vitamin_e":     float(row["vitamin_e"] or 0),
                        "cholesterol":   float(row["cholesterol"] or 0),
                    }
                )
            )

        # Upload to Qdrant
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

        total_migrated += len(points)
        elapsed = time.time() - start_time
        percent = round(total_migrated / total_foods * 100, 1)
        rate = round(total_migrated / elapsed, 1) if elapsed > 0 else 0

        print(f"✅ Batch {batch_num} done | "
              f"{total_migrated}/{total_foods} foods | "
              f"{percent}% | "
              f"{rate} foods/sec")

    conn.close()
    total_time = round(time.time() - start_time, 1)
    print()
    print(f"🎉 Migration complete!")
    print(f"   Total migrated: {total_migrated} foods")
    print(f"   Total time:     {total_time} seconds")
    print(f"   Collection:     {COLLECTION_NAME}")
    print(f"   Dimensions:     {EMBEDDING_DIM}")
    print()
    print("Next step: Update app.py to use Qdrant for food matching!")


if __name__ == "__main__":
    migrate_data()