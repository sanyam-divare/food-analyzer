# AFCD Food Database Importer
# Australian Food Composition Database - Release 3
# Source: https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd
# Run this script to import or update the food database
# Usage: python import_afcd.py

import pandas as pd
import sqlite3
import os

# ── Config ───────────────────────────────────────
DATA_DIR = 'data'
NUTRIENTS_FILE = f'{DATA_DIR}/AFCD Release 3 - Nutrient profiles.xlsx'
FOOD_DETAILS_FILE = f'{DATA_DIR}/AFCD Release 3 - Food Details.xlsx'
DB_FILE = 'food_database.db'

# ── Check files exist ─────────────────────────────
if not os.path.exists(NUTRIENTS_FILE):
    print(f"❌ File not found: {NUTRIENTS_FILE}")
    exit(1)

print("📂 Reading AFCD data files...")
print(f"   {NUTRIENTS_FILE}")

# ── Read Excel ────────────────────────────────────
nutrients = pd.read_excel(
    NUTRIENTS_FILE,
    sheet_name='All solids & liquids per 100 g',
    header=2
)
print(f"✅ Loaded {len(nutrients)} foods from AFCD")

# ── Column mapping ────────────────────────────────
energy_col = 'Energy with dietary fibre, equated \n(kJ)'
protein_col = 'Protein \n(g)'
fat_col     = 'Fat, total \n(g)'
carb_col    = 'Available carbohydrate, without sugar alcohols \n(g)'
fibre_col   = 'Total dietary fibre \n(g)'
sodium_col  = 'Sodium (Na) \n(mg)'

# ── Create database ───────────────────────────────
print(f"\n🗄️  Building SQLite database: {DB_FILE}")
conn = sqlite3.connect(DB_FILE)

# Keep existing foods table (our manual entries)
# Create new AFCD table
conn.execute('DROP TABLE IF EXISTS foods_afcd')
conn.execute('''CREATE TABLE foods_afcd (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    food_key      TEXT,
    food_name     TEXT,
    energy_kcal   REAL,
    protein       REAL,
    fat           REAL,
    carbohydrates REAL,
    fibre         REAL,
    sodium        REAL
)''')

# ── Import data ───────────────────────────────────
count = 0
skipped = 0

for _, row in nutrients.iterrows():
    try:
        food_name = str(row['Food Name'])
        if food_name == 'nan' or food_name == '':
            skipped += 1
            continue

        # Convert kJ to kcal
        energy_kj   = float(row[energy_col]) if pd.notna(row[energy_col]) else 0
        energy_kcal = round(energy_kj / 4.184, 1)
        protein     = float(row[protein_col]) if pd.notna(row[protein_col]) else 0
        fat         = float(row[fat_col])     if pd.notna(row[fat_col])     else 0
        carbs       = float(row[carb_col])    if pd.notna(row[carb_col])    else 0
        fibre       = float(row[fibre_col])   if pd.notna(row[fibre_col])   else 0
        sodium      = float(row[sodium_col])  if pd.notna(row[sodium_col])  else 0

        conn.execute('''
            INSERT INTO foods_afcd
            (food_key, food_name, energy_kcal, protein, fat, carbohydrates, fibre, sodium)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(row['Public Food Key']),
            food_name,
            energy_kcal, protein, fat, carbs, fibre, sodium
        ))
        count += 1

    except Exception as e:
        skipped += 1
        continue

conn.commit()

# ── Summary ───────────────────────────────────────
print(f"✅ Imported: {count} foods")
print(f"⏭️  Skipped:  {skipped} rows")

# ── Test searches ─────────────────────────────────
print("\n🔍 Test searches:")
tests = ['banana', 'chicken', 'rice', 'fish', 'apple']
cursor = conn.cursor()

for food in tests:
    cursor.execute("""
        SELECT food_name, energy_kcal, protein, fat, carbohydrates
        FROM foods_afcd
        WHERE LOWER(food_name) LIKE ?
        LIMIT 1
    """, (f'%{food}%',))
    result = cursor.fetchone()
    if result:
        print(f"  ✅ {result[0][:40]}: {result[1]} kcal")
    else:
        print(f"  ❌ {food}: not found")

conn.close()
print(f"\n🎉 Database ready at: {DB_FILE}")
print("   Run this script again anytime to update with new AFCD releases!")