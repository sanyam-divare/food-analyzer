import os
import sqlite3
from dotenv import load_dotenv
from google import genai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Load environment configs
load_dotenv()

# 1. Initialize Clients
print("🔗 Connecting to Cloud Services...")
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
    prefer_grpc=False  # 🚀 CRITICAL: Tells the client to use pure HTTP REST, bypassing grpcio completely!
)
COLLECTION_NAME = "food_analyzer"
EMBEDDING_DIM = 768  # text-embedding-004 produces 768-dimensional vectors

# 2. Setup Qdrant Collection (Creates it if it doesn't exist)
if not qdrant_client.collection_exists(COLLECTION_NAME):
    print(f"📦 Creating a fresh collection: '{COLLECTION_NAME}'...")
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
    )

def get_gemini_embeddings_batch(texts):
    """Fetches text embeddings in bulk from the Gemini API."""
    try:
        response = gemini_client.models.embed_content(
            model="text-embedding-004",
            contents=texts
        )
        # Extract the vector arrays out of the response object
        return [embedding.values for embedding in response.embeddings]
    except Exception as e:
        print(f"❌ Failed to generate embeddings from Gemini: {e}")
        return None

def migrate_data(batch_size=100):
    """Streams data out of SQLite and upserts it into Qdrant Cloud."""
    conn = sqlite3.connect("foods.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Grab your local rows (Adjust table/column names if yours differ)
    cursor.execute("SELECT food_key, food_name FROM foods_afcd")
    
    batch_rows = []
    total_migrated = 0
    
    print("🚀 Beginning Data Migration Stream...")
    
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break # Entire local database processed!
            
        texts_to_embed = [row["food_name"] for row in rows]
        embeddings = get_gemini_embeddings_batch(texts_to_embed)
        
        if not embeddings:
            print("⚠️ Skipping batch due to embedding failure.")
            continue
            
        points = []
        for i, row in enumerate(rows):
            # Qdrant requires a clean integer or standard UUID for point IDs
            point_id = int(row["food_key"]) 
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embeddings[i],
                    payload={
                        "food_name": row["food_name"],
                        "food_key": row["food_key"]
                    }
                )
            )
            
        # Bulk upload the structured points directly into Qdrant Cloud
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        
        total_migrated += len(points)
        print(f"✅ Successfully migrated {total_migrated} items...")
        
    conn.close()
    print(f"\n🎉 Done! All {total_migrated} items are live in Qdrant Cloud.")

if __name__ == "__main__":
    migrate_data()