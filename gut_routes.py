# ── Gut Health Routes ───────────────────────────────────────────────────────
# Persona 2: Gut Health Tracker
# Blueprint prefix: /gut

from flask import Blueprint, jsonify, request, Response, stream_with_context
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
    stream_gut_with_gemini,
    stream_gut_with_claude,
    save_gut_meal_log,
    get_local_timestamp,
    build_daily_gut_scorecard,
    build_weekly_gut_scorecard,
    build_monthly_gut_scorecard,
    load_gut_profile,
    save_gut_profile,
    delete_gut_profile,
    get_empty_profile,
    check_food_targets_today,
    check_bacteria_progress_today,
    analyse_full_day_with_claude
)

# Supabase cloud sync functions
try:
    from supabase_db import (
        save_gut_profile  as sb_save_profile,
        save_gut_meal     as sb_save_meal,
        resolve_patient_uuid
    )
    SUPABASE_AVAILABLE = True
except Exception:
    SUPABASE_AVAILABLE = False

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
        
        # Load patient profile for personalised prompt
        profile = load_gut_profile(patient_id)

        result = (analyze_gut_with_gemini(image_base64, mime_type,
                                          patient_profile=profile)
                  if provider == 'gemini'
                  else analyze_gut_with_claude(image_base64, mime_type,
                                               patient_profile=profile))

        # result = (analyze_gut_with_gemini(image_base64, mime_type)
        #           if provider == 'gemini'
        #           else analyze_gut_with_claude(image_base64, mime_type))

        if isinstance(result, dict) and result.get('error'):
            return jsonify({"error": result['error']}), 500

        result['timestamp']  = get_local_timestamp(timezone_str)
        result['patient_id'] = patient_id
        result['mode']       = 'gut'
        return jsonify(result)

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/analyze-stream', methods=['POST'])
def gut_analyze_stream():
    """Streaming image analysis via SSE. Original /gut/analyze untouched."""
    try:
        data         = request.get_json() or {}
        image_base64 = data.get('image')
        mime_type    = data.get('mime_type', 'image/jpeg')
        provider     = data.get('provider', 'gemini').lower()
        timezone_str = data.get('timezone', '')
        patient_id   = data.get('patient_id', 'guest')

        if not image_base64:
            def err():
                yield f'data: {json.dumps({"error": "No image provided"})}\n\n'
            return Response(stream_with_context(err()),
                            mimetype='text/event-stream',
                            headers={'Cache-Control': 'no-cache'})

        profile   = load_gut_profile(patient_id)
        timestamp = get_local_timestamp(timezone_str)

        def generate():
            streamer = stream_gut_with_gemini if provider == 'gemini' else stream_gut_with_claude
            for event in streamer(image_base64, mime_type, patient_profile=profile):
                if event.startswith('data: ') and '"done"' in event:
                    try:
                        payload = json.loads(event[6:])
                        if 'done' in payload and isinstance(payload['done'], dict):
                            payload['done']['timestamp']  = timestamp
                            payload['done']['patient_id'] = patient_id
                            payload['done']['mode']       = 'gut'
                            yield f'data: {json.dumps(payload)}\n\n'
                            continue
                    except Exception:
                        pass
                yield event

        return Response(stream_with_context(generate()),
                        mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache',
                                 'X-Accel-Buffering': 'no',
                                 'Connection': 'keep-alive'})
    except Exception as e:
        import traceback; print(traceback.format_exc())
        def err():
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
        return Response(stream_with_context(err()),
                        mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache'})


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

        # Load patient profile for personalised prompt
        profile = load_gut_profile(patient_id)

        result = analyze_gut_with_claude_text(text,
                                              patient_profile=profile)

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


@gut_bp.route('/profile/reset', methods=['POST'])
def gut_reset_profile():
    """
    Actually delete the patient's profile so they see the
    empty/template-selection screen again on next load.
    Used by 'Clear My Data' — does not touch meal history.
    """
    try:
        data       = request.get_json() or {}
        patient_id = data.get('patient_id', 'guest')
        delete_gut_profile(patient_id)
        return jsonify({"status": "reset", "patient_id": patient_id})
    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/meals', methods=['GET'])
def gut_get_meals():
    """Return all meals for a patient since a given date (for cloud sync)."""
    try:
        from gut_engine import load_gut_meals_since
        patient_id = request.args.get('patient_id', 'guest')
        since      = request.args.get('since', '')
        meals      = load_gut_meals_since(patient_id, since)
        return jsonify({"meals": meals, "count": len(meals)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/sync-cloud', methods=['POST'])
def gut_sync_cloud():
    """
    Save profile + last 90 days meals to Supabase.
    Accepts batched meal uploads for large datasets.
    """
    if not SUPABASE_AVAILABLE:
        return jsonify({"error": "Cloud sync unavailable"}), 503

    try:
        data       = request.get_json() or {}
        patient_id = data.get('patient_id', 'guest')
        action     = data.get('action', 'full')

        # ── Profile sync ──────────────────────────────
        if action == 'profile':
            profile = load_gut_profile(patient_id)
            profile['patient_id'] = patient_id
            sb_save_profile(profile)
            return jsonify({"status": "ok", "action": "profile"})

        # ── Meal batch sync ───────────────────────────
        elif action == 'meals':
            meals = data.get('meals', [])
            saved = 0
            for meal in meals:
                meal['patient_id'] = patient_id
                if sb_save_meal(meal):
                    saved += 1
            return jsonify({
                "status": "ok",
                "saved":  saved,
                "total":  len(meals)
            })

        # ── Full sync (profile + meals together) ──────
        elif action == 'full':
            profile = load_gut_profile(patient_id)
            profile['patient_id'] = patient_id
            sb_save_profile(profile)
            meals = data.get('meals', [])
            saved = 0
            for meal in meals:
                meal['patient_id'] = patient_id
                if sb_save_meal(meal):
                    saved += 1
            return jsonify({
                "status": "ok",
                "action": "full",
                "saved":  saved,
                "total":  len(meals)
            })

        return jsonify({"status": "ok"})

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@gut_bp.route('/delete-cloud', methods=['POST'])
def gut_delete_cloud():
    """Delete all patient data from Supabase (Clear My Data)."""
    if not SUPABASE_AVAILABLE:
        return jsonify({"status": "ok"})  # nothing to delete

    try:
        from supabase_db import get_client, resolve_patient_uuid
        data       = request.get_json() or {}
        patient_id = data.get('patient_id', 'guest')

        patient_uuid = resolve_patient_uuid(patient_id)
        if not patient_uuid:
            return jsonify({"status": "ok", "note": "patient not found"})

        sb = get_client()
        sb.table('gut_meals').delete().eq('patient_id', patient_uuid).execute()
        sb.table('gut_profiles').delete().eq('patient_id', patient_uuid).execute()

        return jsonify({"status": "deleted"})

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

@gut_bp.route('/meal/update-time', methods=['POST'])
def gut_update_meal_time():
    '''Update meal timestamp — identified by old timestamp'''
    try:
        data          = request.get_json() or {}
        patient_id    = data.get('patient_id', 'guest')
        old_timestamp = data.get('old_timestamp', '')
        new_timestamp = data.get('new_timestamp', '')

        if not old_timestamp or not new_timestamp:
            return jsonify({"error": "Missing timestamps"}), 400

        log_file = 'gut_meals_log.json'
        if not os.path.exists(log_file):
            return jsonify({"error": "No meal log found"}), 404

        with open(log_file, 'r') as f:
            meals = json.load(f)

        # Find and update the meal
        found = False
        for meal in meals:
            if (meal.get('patient_id') == patient_id and
                    meal.get('timestamp') == old_timestamp):
                meal['timestamp'] = new_timestamp
                meal['date']      = new_timestamp[:10]
                found = True
                break

        if not found:
            return jsonify({"error": "Meal not found"}), 404

        with open(log_file, 'w') as f:
            json.dump(meals, f, indent=2)

        return jsonify({
            "status":        "updated",
            "new_timestamp": new_timestamp,
            "new_date":      new_timestamp[:10]
        })

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# @gut_bp.route('/daily-analysis', methods=['POST'])
# def gut_daily_analysis():
#     ROUTE_CODE = '''
#     @gut_bp.route('/daily-analysis', methods=['POST'])
#     def gut_daily_analysis():
#         """
#         AI holistic analysis of entire day food log.
#         Considers sequencing, FODMAP load, food interactions.
#         """
#         try:
#             data       = request.get_json() or {}
#             patient_id = data.get('patient_id', 'guest')
#             date       = data.get('date', get_today_str())

#             # Load profile and today meals
#             from gut_engine import (
#                 load_gut_profile,
#                 analyse_full_day_with_claude
#             )

#             profile   = load_gut_profile(patient_id)
#             all_meals = load_gut_meals(patient_id)

#             day_meals = [
#                 m for m in all_meals
#                 if m.get('timestamp', '')[:10] == date
#                 or m.get('date', '') == date
#             ]

#             if len(day_meals) < 2:
#                 return jsonify({
#                     "error": "Log at least 2 meals for a day analysis"
#                 }), 400

#             analysis = analyse_full_day_with_claude(day_meals, profile)

#             if analysis.get('error'):
#                 return jsonify({"error": analysis['error']}), 500

#             # Add meal count and date to response
#             analysis['meal_count'] = len(day_meals)
#             analysis['date']       = date

#             return jsonify(analysis)

#         except Exception as e:
#             import traceback; print(traceback.format_exc())
#             return jsonify({"error": str(e)}), 500
#     '''
@gut_bp.route('/daily-analysis', methods=['POST'])
def gut_daily_analysis():
    """AI holistic analysis of entire day food log."""
    try:
        data       = request.get_json() or {}
        patient_id = data.get('patient_id', 'guest')
        date       = data.get('date', get_today_str())

        # Load profile
        from gut_engine import (
            load_gut_profile,
            analyse_full_day_with_claude
        )
        profile   = load_gut_profile(patient_id)

        # Load today's meals
        all_meals = load_gut_meals(patient_id)
        day_meals = [
            m for m in all_meals
            if m.get('timestamp', '')[:10] == date
            or m.get('date', '') == date
        ]

        if len(day_meals) < 2:
            return jsonify({
                "error": "Log at least 2 meals for a day analysis"
            }), 400

        analysis = analyse_full_day_with_claude(day_meals, profile)

        if not analysis:
            return jsonify({"error": "Analysis returned empty"}), 500

        if analysis.get('error'):
            return jsonify({"error": analysis['error']}), 500

        analysis['meal_count'] = len(day_meals)
        analysis['date']       = date

        return jsonify(analysis)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND — Add route to gut_routes.py
# ══════════════════════════════════════════════════════════════════════════════

@gut_bp.route('/instant-log', methods=['POST'])
def gut_instant_log():
    """
    Instantly log a food based on previous analysis.
    No AI call needed — reuses stored analysis.
    """
    try:
        data         = request.get_json() or {}
        patient_id   = data.get('patient_id', 'guest')
        food_name    = data.get('food_name', '')
        timezone_str = data.get('timezone', '')

        if not food_name:
            return jsonify({"error": "No food name provided"}), 400

        # Load patient meals
        all_meals = load_gut_meals(patient_id)

        # Find previous analysis
        from gut_engine import (
            find_previous_food_analysis,
            build_instant_meal
        )
        food, prev_meal = find_previous_food_analysis(
            all_meals, food_name
        )

        if not food:
            return jsonify({
                "error": "no_previous",
                "message": f"No previous analysis found for {food_name}"
            }), 404

        # Build new meal with current timestamp
        new_meal = build_instant_meal(
            patient_id, food, prev_meal, timezone_str
        )

        # Save to log
        log_file = 'gut_meals_log.json'
        import json, os
        meals = []
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                meals = json.load(f)
        meals.append(new_meal)
        with open(log_file, 'w') as f:
            json.dump(meals, f, indent=2)

        return jsonify({
            "status":    "logged",
            "food":      food.get('name'),
            "score":     new_meal['overall_gut_score'],
            "timestamp": new_meal['timestamp']
        })

    except Exception as e:
        import traceback; print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500