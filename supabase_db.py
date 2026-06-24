# ══════════════════════════════════════════════════════════════════════════════
# supabase_db.py  —  Database helper module
# Replaces all JSON file operations with Supabase queries
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Client singleton ──────────────────────────────────────────────────────────
_supabase_client = None

def get_client():
    """Returns Supabase client — creates once, reuses after."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set in .env"
            )
        _supabase_client = create_client(url, key)
    return _supabase_client


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — PIN validation
# ══════════════════════════════════════════════════════════════════════════════

def validate_pin(pin):
    """
    Validate PIN against patients table.
    Returns patient dict or None if invalid.
    """
    try:
        sb  = get_client()
        res = sb.table('patients') \
                .select('id, name, pin') \
                .eq('pin', pin.strip().lower()) \
                .execute()
        if res.data:
            return res.data[0]
        return None
    except Exception as e:
        print(f'[supabase_db] validate_pin error: {e}')
        return None


def get_patient_by_id(patient_id):
    """Get patient record by UUID."""
    try:
        sb  = get_client()
        res = sb.table('patients') \
                .select('id, name, pin') \
                .eq('id', patient_id) \
                .execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f'[supabase_db] get_patient_by_id error: {e}')
        return None


# ══════════════════════════════════════════════════════════════════════════════
# GUT PROFILE
# ══════════════════════════════════════════════════════════════════════════════

def get_empty_profile(patient_id=''):
    """Returns empty profile structure."""
    return {
        "patient_id":    patient_id,
        "name":          "",
        "test_date":     "",
        "test_provider": "",
        "doctor":        "",
        "metrics": {
            "evenness":  0,
            "diversity": 0,
            "fb_ratio":  0
        },
        "functions": {
            "overall_health":    {"helpful": 0, "harmful": 0},
            "immunity":          {"helpful": 0, "harmful": 0},
            "gi_health":         {"helpful": 0, "harmful": 0},
            "mental_wellness":   {"helpful": 0, "harmful": 0},
            "weight_management": {"helpful": 0, "harmful": 0},
            "sugar_metabolism":  {"helpful": 0, "harmful": 0}
        },
        "bacteria_boost":  [],
        "bacteria_reduce": [],
        "food_targets":    [],
        "foods_add":       [],
        "foods_reduce":    []
    }


def load_gut_profile(patient_id):
    """
    Load gut profile for patient.
    Falls back to JSON file if Supabase unavailable.
    Returns empty profile if none found.
    """
    try:
        sb  = get_client()

        # Look up patient UUID from name/pin identifier
        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            return get_empty_profile(patient_id)

        res = sb.table('gut_profiles') \
                .select('*') \
                .eq('patient_id', patient_uuid) \
                .execute()

        if not res.data:
            return get_empty_profile(patient_id)

        row     = res.data[0]
        profile = get_empty_profile(patient_id)

        # Map database columns back to profile structure
        profile.update({
            # "name":          row.get('name', ''),
            "test_date":     row.get('test_date', ''),
            "test_provider": row.get('test_provider', ''),
            "doctor":        row.get('doctor', ''),
            "metrics":       row.get('metrics')       or profile['metrics'],
            "functions":     row.get('functions')     or profile['functions'],
            "bacteria_boost":  row.get('bacteria_boost')  or [],
            "bacteria_reduce": row.get('bacteria_reduce') or [],
            "food_targets":    row.get('food_targets')    or [],
            "foods_add":       row.get('foods_add')       or [],
            "foods_reduce":    row.get('foods_reduce')    or [],
        })

        return profile

    except Exception as e:
        print(f'[supabase_db] load_gut_profile error: {e}')
        # Fallback to JSON file
        return _load_profile_from_json(patient_id)


def save_gut_profile(profile_data):
    """
    Save gut profile to Supabase.
    Uses upsert — creates if not exists, updates if exists.
    """
    try:
        sb         = get_client()
        patient_id = profile_data.get('patient_id', 'guest')

        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            print(f'[supabase_db] Patient not found: {patient_id}')
            return False

        row = {
            "patient_id":    patient_uuid,
            # "name":          profile_data.get('name', ''),
            "test_date":     profile_data.get('test_date', ''),
            "test_provider": profile_data.get('test_provider', ''),
            "doctor":        profile_data.get('doctor', ''),
            "condition":     profile_data.get('condition', ''),
            "metrics":       profile_data.get('metrics', {}),
            "functions":     profile_data.get('functions', {}),
            "bacteria_boost":  profile_data.get('bacteria_boost', []),
            "bacteria_reduce": profile_data.get('bacteria_reduce', []),
            "food_targets":    profile_data.get('food_targets', []),
            "foods_add":       profile_data.get('foods_add', []),
            "foods_reduce":    profile_data.get('foods_reduce', []),
            "updated_at":      datetime.now(timezone.utc).isoformat()
        }

        sb.table('gut_profiles').upsert(
            row, on_conflict='patient_id'
        ).execute()

        return True

    except Exception as e:
        print(f'[supabase_db] save_gut_profile error: {e}')
        return False


# ══════════════════════════════════════════════════════════════════════════════
# GUT MEALS
# ══════════════════════════════════════════════════════════════════════════════

def save_gut_meal(meal_data):
    """Save a confirmed gut meal to Supabase."""
    try:
        sb         = get_client()
        patient_id = meal_data.get('patient_id', 'guest')

        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            print(f'[supabase_db] Patient not found: {patient_id}')
            return False

        # Extract date from timestamp
        timestamp = meal_data.get('timestamp', '')
        date      = timestamp[:10] if timestamp else \
                    datetime.now().strftime('%Y-%m-%d')

        row = {
            "patient_id":        patient_uuid,
            "timestamp":         timestamp,
            "date":              date,
            "meal_description":  meal_data.get('meal_description', ''),
            "foods":             meal_data.get('foods', []),
            "gut_scores":        meal_data.get('gut_scores', {}),
            "overall_gut_score": meal_data.get('overall_gut_score', 0),
            "gut_notes":         meal_data.get('gut_notes', ''),
        }

        sb.table('gut_meals').insert(row).execute()
        return True

    except Exception as e:
        print(f'[supabase_db] save_gut_meal error: {e}')
        return False


def load_gut_meals(patient_id, limit=100):
    """Load all gut meals for a patient, newest last."""
    try:
        sb           = get_client()
        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            return []

        res = sb.table('gut_meals') \
                .select('*') \
                .eq('patient_id', patient_uuid) \
                .order('timestamp', desc=False) \
                .limit(limit) \
                .execute()

        # Convert back to app format
        meals = []
        for row in res.data:
            meal = {
                "patient_id":        patient_id,
                "timestamp":         row.get('timestamp', ''),
                "date":              row.get('date', ''),
                "meal_description":  row.get('meal_description', ''),
                "foods":             row.get('foods', []),
                "gut_scores":        row.get('gut_scores', {}),
                "overall_gut_score": row.get('overall_gut_score', 0),
                "gut_notes":         row.get('gut_notes', ''),
            }
            meals.append(meal)

        return meals

    except Exception as e:
        print(f'[supabase_db] load_gut_meals error: {e}')
        return []


def load_gut_meals_by_date(patient_id, date):
    """Load gut meals for a specific date."""
    try:
        sb           = get_client()
        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            return []

        res = sb.table('gut_meals') \
                .select('*') \
                .eq('patient_id', patient_uuid) \
                .eq('date', date) \
                .order('timestamp', desc=False) \
                .execute()

        meals = []
        for row in res.data:
            meal = {
                "patient_id":        patient_id,
                "timestamp":         row.get('timestamp', ''),
                "date":              row.get('date', ''),
                "meal_description":  row.get('meal_description', ''),
                "foods":             row.get('foods', []),
                "gut_scores":        row.get('gut_scores', {}),
                "overall_gut_score": row.get('overall_gut_score', 0),
                "gut_notes":         row.get('gut_notes', ''),
            }
            meals.append(meal)

        return meals

    except Exception as e:
        print(f'[supabase_db] load_gut_meals_by_date error: {e}')
        return []


def load_gut_meals_by_date_range(patient_id, start_date, end_date):
    """Load gut meals between two dates (inclusive)."""
    try:
        sb           = get_client()
        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            return []

        res = sb.table('gut_meals') \
                .select('*') \
                .eq('patient_id', patient_uuid) \
                .gte('date', start_date) \
                .lte('date', end_date) \
                .order('timestamp', desc=False) \
                .execute()

        meals = []
        for row in res.data:
            meal = {
                "patient_id":        patient_id,
                "timestamp":         row.get('timestamp', ''),
                "date":              row.get('date', ''),
                "meal_description":  row.get('meal_description', ''),
                "foods":             row.get('foods', []),
                "gut_scores":        row.get('gut_scores', {}),
                "overall_gut_score": row.get('overall_gut_score', 0),
                "gut_notes":         row.get('gut_notes', ''),
            }
            meals.append(meal)

        return meals

    except Exception as e:
        print(f'[supabase_db] load_gut_meals_by_date_range error: {e}')
        return []


# ══════════════════════════════════════════════════════════════════════════════
# PATIENT RESOLUTION
# Handles both UUID and name-based patient_id for backwards compatibility
# ══════════════════════════════════════════════════════════════════════════════

# Cache to avoid repeated DB lookups for same patient
_patient_cache = {}

def resolve_patient_uuid(patient_id):
    """
    Convert patient_id (PIN string) to Supabase UUID.
    App sends PIN as patient_id (e.g. '20262026').
    Searches patients table by pin column first,
    then falls back to name for legacy compatibility.
    """
    if not patient_id:
        return None

    # Check cache first
    if patient_id in _patient_cache:
        return _patient_cache[patient_id]

    try:
        sb = get_client()

        # Already a UUID format? Use directly.
        if len(str(patient_id)) == 36 and '-' in str(patient_id):
            _patient_cache[patient_id] = patient_id
            return patient_id

        # Search by PIN first (primary method)
        res = sb.table('patients') \
                .select('id') \
                .eq('pin', str(patient_id)) \
                .execute()

        if res.data:
            uuid = res.data[0]['id']
            _patient_cache[patient_id] = uuid
            return uuid

        # Fallback — search by name (legacy)
        res2 = sb.table('patients') \
                 .select('id') \
                 .ilike('name', str(patient_id)) \
                 .execute()

        if res2.data:
            uuid = res2.data[0]['id']
            _patient_cache[patient_id] = uuid
            return uuid

        return None

    except Exception as e:
        print(f'[supabase_db] resolve_patient_uuid error: {e}')
        return None


# ══════════════════════════════════════════════════════════════════════════════
# JSON FALLBACK — used if Supabase unavailable
# ══════════════════════════════════════════════════════════════════════════════

def _load_profile_from_json(patient_id):
    """Fallback: load from local JSON file."""
    try:
        if os.path.exists('gut_patient_profile.json'):
            with open('gut_patient_profile.json', 'r') as f:
                data = json.load(f)
            if isinstance(data, dict) and \
               data.get('patient_id') == patient_id:
                return data
    except Exception:
        pass
    return get_empty_profile(patient_id)


# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION — import existing JSON data into Supabase
# Run once: python supabase_db.py
# ══════════════════════════════════════════════════════════════════════════════

def migrate_json_to_supabase():
    """
    One-time migration of existing JSON files to Supabase.
    Safe to run multiple times — skips existing data.
    """
    print('Starting migration...')
    migrated_meals   = 0
    migrated_profile = False

    # ── Migrate gut meals ─────────────────────────────────────────────────
    if os.path.exists('gut_meals_log.json'):
        with open('gut_meals_log.json', 'r') as f:
            meals = json.load(f)

        print(f'Found {len(meals)} meals to migrate...')

        for meal in meals:
            success = save_gut_meal(meal)
            if success:
                migrated_meals += 1

        print(f'✅ Migrated {migrated_meals}/{len(meals)} meals')
    else:
        print('No gut_meals_log.json found — skipping meals')

    # ── Migrate gut profile ───────────────────────────────────────────────
    if os.path.exists('gut_patient_profile.json'):
        with open('gut_patient_profile.json', 'r') as f:
            profile = json.load(f)

        success = save_gut_profile(profile)
        if success:
            migrated_profile = True
            print('✅ Migrated gut profile')
        else:
            print('❌ Profile migration failed')
    else:
        print('No gut_patient_profile.json found — skipping profile')

    print(f'\nMigration complete!')
    print(f'Meals:   {migrated_meals}')
    print(f'Profile: {"✅" if migrated_profile else "❌ not found"}')


if __name__ == '__main__':
    migrate_json_to_supabase()
