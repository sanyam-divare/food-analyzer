# Generate Gemini embeddings for all foods in AFCD database
# Run once: python generate_embeddings.py
# Re-run anytime to update embeddings

import sqlite3
import requests
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DB_FILE = 'food_database.db'
MODEL = 'models/gemini-embedding-2'
BATCH_DELAY = 0.1  # seconds between requests

def get_embedding(text):
    url = f'https://generativelanguage.googleapis.com/v1beta/{MODEL}:embedContent?key={GEMINI_API_KEY}'
    payload = {
        'model': MODEL,
        'content': {'parts': [{'text': text}]}
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json()['embedding']['values']
    elif response.status_code == 429:
        print("Rate limited! Waiting 60 seconds...")
        time.sleep(60)
        return get_embedding(text)
    else:
        print(f"Error {response.status_code}: {response.text[:100]}")
        return None

def main():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Get foods without embeddings
    cursor.execute("""
        SELECT id, food_key, food_name
        FROM foods_afcd
        WHERE embedding IS NULL
        ORDER BY id
    """)
    foods = cursor.fetchall()
    total = len(foods)

    if total == 0:
        print("✅ All foods already have embeddings!")
        conn.close()
        return

    print(f"📊 Generating embeddings for {total} foods...")
    print(f"   Model: {MODEL}")
    print(f"   Estimated time: {total * BATCH_DELAY / 60:.1f} mins minimum")
    print(f"   (Rate limit pauses may add time)\n")

    success = 0
    failed = 0

    for i, (food_id, food_key, food_name) in enumerate(foods):
        # Create rich text for better embedding
        embed_text = food_name.lower()

        vector = get_embedding(embed_text)

        if vector:
            conn.execute("""
                UPDATE foods_afcd
                SET embedding = ?
                WHERE id = ?
            """, (json.dumps(vector), food_id))

            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"  Progress: {i+1}/{total} ({((i+1)/total*100):.1f}%)")

            success += 1
        else:
            failed += 1
            print(f"  ❌ Failed: {food_name}")

        time.sleep(BATCH_DELAY)

    conn.commit()
    conn.close()

    print(f"\n✅ Done!")
    print(f"   Success: {success}")
    print(f"   Failed:  {failed}")
    print(f"   Total:   {total}")

if __name__ == '__main__':
    main()