# ── Gut Health Routes ───────────────────────────────────────────────────────
# Persona 2: Gut Health Tracker
# Blueprint prefix: /gut

from flask import Blueprint, jsonify, request
from datetime import datetime
import json, os

# from supabase_db import (
#     load_gut_meals,
#     load_gut_profile,
#     save_gut_profile,
#     save_gut_meal,
#     validate_pin as db_validate_pin
# )

from gut_engine import (
    analyze_gut_with_claude,
    analyze_gut_with_gemini,
    analyze_gut_with_claude_text,
    save_gut_meal_log,
    get_local_timestamp,
    build_daily_gut_scorecard,
    build_weekly_gut_scorecard,
    build_monthly_gut_scorecard,
    load_gut_profile,
    save_gut_profile,
    get_empty_profile,
    check_food_targets_today,
    check_bacteria_progress_today,
)

gut_bp = Blueprint('gut', __name__, url_prefix='/gut')


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_gut_meals(patient_id):
    """Load all gut meals for a patient from file."""
    log_file = 'gut_meals_log.json'
    if not os.path.exists(log_file):
        return []
    with open(log_file, 'r') as f:
        log = json.load(f)
    return [m for m in log if m.get('patient_id') == patient_id]


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


# ── Analyze routes ────────────────────────────────────────────────────────────

@gut_bp.route('/analyze', methods=['POST'])
def gut_analyze():
    """Analyze food image with gut-specific Claude prompt."""
    try:
        data         = request.get_json() or {}
        image_base64 = data.get('image')
        mime_type    = data.get('mime_type', 'image/jpeg')
        provider     = data.get('provider', 'claude').lower()
        timezone_str = data.get('timezone', '')
        patient_id   = data.get('patient_id', 'guest')

        if not image_base64:
            return jsonify({"error": "No image provided"}), 400

        result = (analyze_gut_with_gemini(image_base64, mime_type)
                  if provider == 'gemini'
                  else analyze_gut_with_claude(image_base64, mime_type))

        if isinstance(result, dict) and result.get('error'):
            return jsonify({"error": result['error']}), 500

        result['timestamp']  = get_local_timestamp(timezone_str)
        result['patient_id'] = patient_id
        result['mode']       = 'gut'
        return jsonify(result)

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/analyze-voice', methods=['POST'])
def gut_analyze_voice():
    """Analyze voice/text description with gut-specific prompt."""
    try:
        data         = request.get_json() or {}
        text         = data.get('text', '')
        timezone_str = data.get('timezone', '')
        patient_id   = data.get('patient_id', 'guest')

        if not text:
            return jsonify({"error": "No text provided"}), 400

        result = analyze_gut_with_claude_text(text)

        if isinstance(result, dict) and result.get('error'):
            return jsonify({"error": result['error']}), 500

        result['timestamp']  = get_local_timestamp(timezone_str)
        result['patient_id'] = patient_id
        result['mode']       = 'gut'
        return jsonify(result)

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/confirm-meal', methods=['POST'])
def gut_confirm_meal():
    """Save gut meal only when user explicitly confirms."""
    try:
        data         = request.get_json() or {}
        timezone_str = data.get('timezone', '')

        meal_data = {
            "patient_id":        data.get('patient_id', 'guest'),
            "meal_description":  data.get('meal_description', ''),
            "foods":             data.get('foods', []),
            "gut_scores":        data.get('gut_scores', {}),
            "timestamp":         data.get('timestamp') or get_local_timestamp(timezone_str),
            "overall_gut_score": data.get('overall_gut_score', 0),
            "gut_notes":         data.get('gut_notes', ''),
        }

        save_gut_meal_log(meal_data)
        return jsonify({"status": "saved"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── History routes ────────────────────────────────────────────────────────────

@gut_bp.route('/history', methods=['GET'])
def gut_history():
    try:
        patient_id = request.args.get('patient_id', 'guest')
        meals      = load_gut_meals(patient_id)
        return jsonify(meals[-20:])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/history/daily', methods=['GET'])
def gut_history_daily():
    try:
        patient_id  = request.args.get('patient_id', 'guest')
        target_date = request.args.get('date', get_today_str())
        meals       = load_gut_meals(patient_id)

        day_meals = [
            m for m in meals
            if m.get('timestamp', '').startswith(target_date)
            or m.get('date', '') == target_date
        ]

        scores      = [m.get('overall_gut_score', 0)
                       for m in day_meals if m.get('overall_gut_score')]
        daily_score = round(sum(scores) / len(scores), 1) if scores else 0

        return jsonify({
            "date":            target_date,
            "meals":           day_meals,
            "meal_count":      len(day_meals),
            "daily_gut_score": daily_score
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Scorecard routes ──────────────────────────────────────────────────────────

@gut_bp.route('/scorecard/daily', methods=['GET'])
def gut_scorecard_daily():
    try:
        patient_id  = request.args.get('patient_id', 'guest')
        target_date = request.args.get('date', get_today_str())
        meals       = load_gut_meals(patient_id)

        day_meals = [
            m for m in meals
            if m.get('timestamp', '').startswith(target_date)
            or m.get('date', '') == target_date
        ]

        scorecard = build_daily_gut_scorecard(day_meals, target_date)
        return jsonify(scorecard)

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/scorecard/weekly', methods=['GET'])
def gut_scorecard_weekly():
    try:
        from datetime import timedelta
        patient_id = request.args.get('patient_id', 'guest')
        today      = datetime.now()
        monday     = today - timedelta(days=today.weekday())
        week_start = request.args.get('week_start',
                                      monday.strftime("%Y-%m-%d"))
        meals     = load_gut_meals(patient_id)
        scorecard = build_weekly_gut_scorecard(meals, week_start)
        return jsonify(scorecard)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/scorecard/monthly', methods=['GET'])
def gut_scorecard_monthly():
    try:
        patient_id = request.args.get('patient_id', 'guest')
        now        = datetime.now()
        year       = int(request.args.get('year',  now.year))
        month      = int(request.args.get('month', now.month))
        meals      = load_gut_meals(patient_id)
        scorecard  = build_monthly_gut_scorecard(meals, year, month)
        return jsonify(scorecard)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Profile routes ────────────────────────────────────────────────────────────

@gut_bp.route('/profile', methods=['GET'])
def gut_get_profile():
    """Return the patient's gut profile."""
    try:
        patient_id = request.args.get('patient_id', 'guest')
        profile    = load_gut_profile(patient_id)
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/profile', methods=['POST'])
def gut_save_profile():
    """Save / update the patient's gut profile."""
    try:
        data       = request.get_json() or {}
        patient_id = data.get('patient_id', 'guest')

        # Load existing profile so we do a merge, not a full replace
        existing = load_gut_profile(patient_id)
        existing.update(data)           # merge new data over existing
        existing['patient_id'] = patient_id

        save_gut_profile(existing)
        return jsonify({"status": "saved", "profile": existing})

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ── Food Plan route ───────────────────────────────────────────────────────────

@gut_bp.route('/food-plan', methods=['GET'])
def gut_food_plan():
    """
    Return today's food-target progress and bacteria-boost progress
    based on the patient's profile + today's confirmed meals.
    """
    try:
        patient_id  = request.args.get('patient_id', 'guest')
        target_date = request.args.get('date', get_today_str())

        profile   = load_gut_profile(patient_id)
        all_meals = load_gut_meals(patient_id)

        today_meals = [
            m for m in all_meals
            if m.get('timestamp', '').startswith(target_date)
            or m.get('date', '') == target_date
        ]

        food_progress     = check_food_targets_today(profile, today_meals)
        bacteria_progress = check_bacteria_progress_today(profile, today_meals)

        # Build a quick summary of foods eaten today
        eaten_today = {}
        for meal in today_meals:
            for food in meal.get('foods', []):
                name   = food.get('name', '')
                grams  = food.get('estimated_grams', 0)
                eaten_today[name] = eaten_today.get(name, 0) + grams

        return jsonify({
            "date":               target_date,
            "food_progress":      food_progress,
            "bacteria_progress":  bacteria_progress,
            "eaten_today":        eaten_today,
            "foods_add":          profile.get('foods_add', []),
            "foods_reduce":       profile.get('foods_reduce', []),
            "has_profile":        bool(profile.get('bacteria_boost') or
                                       profile.get('food_targets'))
        })

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
