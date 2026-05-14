# AFCD Food Database Importer
# Australian Food Composition Database - Release 3
# Source: https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd
# Run this script to import or update the food database
# Usage: python import_afcd.py

import pandas as pd
import sqlite3
import os

# ── Config ───────────────────────────────────────
DATA_DIR       = 'data'
NUTRIENTS_FILE = f'{DATA_DIR}/AFCD Release 3 - Nutrient profiles.xlsx'
DB_FILE        = 'food_database.db'

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
energy_col      = 'Energy with dietary fibre, equated \n(kJ)'
protein_col     = 'Protein \n(g)'
fat_col         = 'Fat, total \n(g)'
carb_col        = 'Available carbohydrate, without sugar alcohols \n(g)'
fibre_col       = 'Total dietary fibre \n(g)'
sodium_col      = 'Sodium (Na) \n(mg)'
calcium_col     = 'Calcium (Ca) \n(mg)'
iron_col        = 'Iron (Fe) \n(mg)'
magnesium_col   = 'Magnesium (Mg) \n(mg)'
potassium_col   = 'Potassium (K) \n(mg)'
zinc_col        = 'Zinc (Zn) \n(mg)'
vitamin_a_col   = 'Vitamin A retinol equivalents \n(ug)'
vitamin_c_col   = 'Vitamin C \n(mg)'
vitamin_d_col   = 'Vitamin D3 equivalents \n(ug)'
vitamin_e_col   = 'Vitamin E \n(mg)'
cholesterol_col = 'Cholesterol \n(mg)'
sugars_col      = 'Total sugars (g)'

# ── Create database ───────────────────────────────
print(f"\n🗄️  Building SQLite database: {DB_FILE}")
conn = sqlite3.connect(DB_FILE)

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
    sodium        REAL,
    calcium       REAL,
    iron          REAL,
    magnesium     REAL,
    potassium     REAL,
    zinc          REAL,
    vitamin_a     REAL,
    vitamin_c     REAL,
    vitamin_d     REAL,
    vitamin_e     REAL,
    cholesterol   REAL,
    sugars        REAL
)''')

# ── Import data ───────────────────────────────────
count   = 0
skipped = 0

for _, row in nutrients.iterrows():
    try:
        food_name = str(row['Food Name'])
        if food_name == 'nan' or food_name == '':
            skipped += 1
            continue

        def safe(col):
            try:
                return float(row[col]) if pd.notna(row[col]) else 0
            except:
                return 0

        # Convert kJ to kcal
        energy_kcal = round(safe(energy_col) / 4.184, 1)

        conn.execute('''
            INSERT INTO foods_afcd (
                food_key, food_name, energy_kcal,
                protein, fat, carbohydrates, fibre, sodium,
                calcium, iron, magnesium, potassium, zinc,
                vitamin_a, vitamin_c, vitamin_d, vitamin_e,
                cholesterol, sugars
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(row['Public Food Key']),
            food_name,
            energy_kcal,
            safe(protein_col),
            safe(fat_col),
            safe(carb_col),
            safe(fibre_col),
            safe(sodium_col),
            safe(calcium_col),
            safe(iron_col),
            safe(magnesium_col),
            safe(potassium_col),
            safe(zinc_col),
            safe(vitamin_a_col),
            safe(vitamin_c_col),
            safe(vitamin_d_col),
            safe(vitamin_e_col),
            safe(cholesterol_col),
            safe(sugars_col)
        ))
        count += 1

    except Exception as e:
        skipped += 1
        continue

conn.commit()

# ── Summary ───────────────────────────────────────
print(f"✅ Imported: {count} foods")
print(f"⏭️  Skipped:  {skipped} rows")

# ── Test search ───────────────────────────────────
print("\n🔍 Test searches:")
tests = ['banana', 'chicken', 'rice', 'salmon', 'broccoli']
cursor = conn.cursor()

for food in tests:
    cursor.execute("""
        SELECT food_name, energy_kcal, protein, calcium, vitamin_c, potassium
        FROM foods_afcd
        WHERE LOWER(food_name) LIKE ?
        LIMIT 1
    """, (f'%{food}%',))
    result = cursor.fetchone()
    if result:
        print(f"  ✅ {result[0][:45]}")
        print(f"     {result[1]} kcal | protein {result[2]}g | Ca {result[3]}mg | VitC {result[4]}mg | K {result[5]}mg")
    else:
        print(f"  ❌ {food}: not found")

conn.close()
print(f"\n🎉 Database ready with 19 nutrients per food!")
print(f"   Run anytime to update with new AFCD releases.")