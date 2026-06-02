# ── Gut Health Routes ───────────────────────────
# Persona 2: Gut Health Mode

from flask import Blueprint, jsonify, request, g
from datetime import datetime
import json
import os
from gut_engine import (
    analyze_gut_with_claude,
    analyze_gut_with_gemini,
    save_gut_meal_log,
    get_local_timestamp,
    build_daily_gut_scorecard,    # ← add these
    build_weekly_gut_scorecard,
    build_monthly_gut_scorecard)


gut_bp = Blueprint('gut', __name__, url_prefix='/gut')


@gut_bp.route('/analyze', methods=['POST'])
def gut_analyze():
    """Analyze food image with gut-specific Claude prompt"""
    try:
        data = request.get_json() or {}
        image_base64 = data.get('image')
        mime_type    = data.get('mime_type', 'image/jpeg')
        provider     = data.get('provider', 'claude').lower()
        timezone_str = data.get('timezone', '')
        patient_id   = data.get('patient_id', 'guest')

        if not image_base64:
            return jsonify({"error": "No image provided"}), 400

        # Call gut-specific analysis
        if provider == 'gemini':
            result = analyze_gut_with_gemini(image_base64, mime_type)
        else:
            result = analyze_gut_with_claude(image_base64, mime_type)

        if isinstance(result, dict) and result.get('error'):
            return jsonify({"error": result['error']}), 500

        # Add metadata
        result['timestamp'] = get_local_timestamp(timezone_str)
        result['patient_id'] = patient_id
        result['mode'] = 'gut'

        return jsonify(result)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/confirm-meal', methods=['POST'])
def gut_confirm_meal():
    """Save gut meal only when user confirms"""
    try:
        data = request.get_json() or {}
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


@gut_bp.route('/history', methods=['GET'])
def gut_history():
    """Get gut meal history"""
    try:
        patient_id = request.args.get('patient_id', 'guest')
        log_file   = 'gut_meals_log.json'

        if not os.path.exists(log_file):
            return jsonify([])

        with open(log_file, 'r') as f:
            log = json.load(f)

        # Filter by patient
        patient_log = [
            m for m in log
            if m.get('patient_id') == patient_id
        ]

        return jsonify(patient_log[-20:])

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/history/daily', methods=['GET'])
def gut_history_daily():
    """Get today's gut meals"""
    try:
        patient_id  = request.args.get('patient_id', 'guest')
        target_date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
        log_file    = 'gut_meals_log.json'

        if not os.path.exists(log_file):
            return jsonify({"date": target_date, "meals": [], "daily_gut_score": 0})

        with open(log_file, 'r') as f:
            log = json.load(f)

        day_meals = [
            m for m in log
            if m.get('patient_id') == patient_id
            and (m.get('timestamp', '').startswith(target_date)
                 or m.get('date', '') == target_date)
        ]

        # Calculate daily gut score (average of meal scores)
        scores = [m.get('overall_gut_score', 0) for m in day_meals if m.get('overall_gut_score')]
        daily_score = round(sum(scores) / len(scores), 1) if scores else 0

        return jsonify({
            "date":             target_date,
            "meals":            day_meals,
            "meal_count":       len(day_meals),
            "daily_gut_score":  daily_score
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/scorecard/daily', methods=['GET'])
def gut_scorecard_daily():
    try:
        patient_id  = request.args.get('patient_id', 'guest')
        target_date = request.args.get('date',
                      datetime.now().strftime("%Y-%m-%d"))

        meals = load_gut_meals(patient_id)
        day_meals = [
            m for m in meals
            if m.get('timestamp', '').startswith(target_date)
            or m.get('date', '') == target_date
        ]

        scorecard = build_daily_gut_scorecard(day_meals, target_date)
        return jsonify(scorecard)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/scorecard/weekly', methods=['GET'])
def gut_scorecard_weekly():
    try:
        from datetime import datetime, timedelta
        patient_id = request.args.get('patient_id', 'guest')

        # Default to current week Monday
        today      = datetime.now()
        monday     = today - timedelta(days=today.weekday())
        week_start = request.args.get(
            'week_start', monday.strftime("%Y-%m-%d")
        )

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

        meals     = load_gut_meals(patient_id)
        scorecard = build_monthly_gut_scorecard(meals, year, month)
        return jsonify(scorecard)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def load_gut_meals(patient_id):
    """Helper — load all gut meals for a patient"""
    log_file = 'gut_meals_log.json'
    if not os.path.exists(log_file):
        return []
    with open(log_file, 'r') as f:
        log = json.load(f)
    return [m for m in log if m.get('patient_id') == patient_id]