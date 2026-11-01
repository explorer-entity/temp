from flask import Flask, jsonify, request, send_from_directory, g, Response, stream_with_context
import os
import re
import json
import time
import queue
import secrets
import threading
import statistics
import html as _html
from collections import defaultdict
from werkzeug.security import generate_password_hash, check_password_hash
from setup_db import init_db
import sqlite3
import math
from datetime import datetime, timezone, timedelta
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

DB_PATH = os.environ.get("MANOVA_DB") or os.path.join(BASE_DIR, "smriti.db")  # absolute: independent of the working directory
init_db(DB_PATH)  # create / migrate tables on every start, so a forgotten setup step cannot break the app
# MANOVA_AUTH=off restores the old open demo mode (no login). Default is ON.
AUTH_REQUIRED = os.environ.get('MANOVA_AUTH', 'on').lower() != 'off'
RETENTION_DAYS = int(os.environ.get('LOCATION_RETENTION_DAYS', '30'))
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return send_from_directory(STATIC_DIR, "home.html")

STAGE_BASELINE = {'Early': 0.85, 'Moderate': 0.65, 'Severe': 0.45}

@app.route('/sw.js')
def service_worker():
    # Must be served from the site root so its scope can be '/'
    resp = send_from_directory(STATIC_DIR, "sw.js")
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/manifest.json')
def manifest():
    return send_from_directory(STATIC_DIR, "manifest.json")

def bad_request(message, **extra):
    return jsonify(dict(status="error", message=message, **extra)), 400

@app.route('/api/set_stage', methods=['POST'])
def set_stage():
    data = request.get_json() or {}
    if 'user_id' not in data or data.get('stage') not in STAGE_BASELINE:
        return bad_request("user_id and stage (Early/Moderate/Severe) are required")
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO Users (id, name, stage) VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET stage = excluded.stage
    ''', (data['user_id'], data.get('name', 'Patient'), data['stage']))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "stage": data['stage']})

@app.route('/api/save_score', methods=['POST'])
def save_score():
    data = request.get_json() or {}
    for field in ('user_id', 'game_type', 'score'):
        if field not in data:
            return jsonify({"status":"error", "message":f"Missing field: {field}"}), 400

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO GameSessions (user_id, game_type, score, difficulty, max_score, timestamp)
        VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
    ''', (int(data['user_id']), data['game_type'], int(data['score']), data.get('difficulty', 'Easy'),
          int(data['max_score']) if data.get('max_score') else None, _client_time(data)))
    conn.commit(); conn.close()
    return jsonify({"status":"success", "message":"Score saved to database"})

@app.route('/api/progress/<int:user_id>')
def get_progress(user_id):
    conn = get_db_connection()

    rows = conn.execute('''
        SELECT game_type, score, difficulty, timestamp
        FROM GameSessions
        WHERE user_id = ?
        ORDER BY id DESC
    ''', (user_id,)).fetchall()

    total_games = conn.execute('''
        SELECT COUNT(*) AS count FROM GameSessions WHERE user_id = ?
    ''', (user_id,)).fetchone()['count']

    word_picture = conn.execute('''
        SELECT MAX(score) AS best, COUNT(*) AS count
        FROM GameSessions
        WHERE user_id = ? AND game_type = 'word_picture_match'
    ''', (user_id,)).fetchone()

    conn.close()

    return jsonify({
        "user_id": user_id,
        "total_games": total_games,
        "word_picture_best": word_picture['best'] or 0,
        "word_picture_games": word_picture['count'] or 0,
        "history": [dict(row) for row in rows]
    })

consecutive_outside_tracker = {}  # in-memory, resets if the server restarts

@app.route('/api/update_location', methods=['POST'])
def update_location():
    data = request.get_json() or {}
    # Accept both canonical keys and short aliases (lat/lng) for robustness.
    if 'latitude' not in data and 'lat' in data:
        data['latitude'] = data['lat']
    if 'longitude' not in data and 'lng' in data:
        data['longitude'] = data['lng']
    missing = [f for f in ('user_id', 'latitude', 'longitude') if f not in data]
    if missing:
        return jsonify({"status": "error", "missing": missing}), 400
    try:
        data['latitude'], data['longitude'] = float(data['latitude']), float(data['longitude'])
        data['user_id'] = int(data['user_id'])
    except (TypeError, ValueError):
        return bad_request("user_id, latitude and longitude must be numeric")
    if not (-90 <= data['latitude'] <= 90 and -180 <= data['longitude'] <= 180):
        return bad_request("latitude/longitude out of range")
    conn = get_db_connection()
    if AUTH_REQUIRED:  # consent is enforced server-side: revoking it stops ingestion
        who = conn.execute('SELECT location_consent FROM Users WHERE id = ?', (data['user_id'],)).fetchone()
        if not who or not who['location_consent']:
            conn.close()
            return jsonify({"status": "error", "message": "location consent not given"}), 403
    conn.execute('INSERT INTO Locations (user_id, latitude, longitude, timestamp) VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))',
        (data['user_id'], data['latitude'], data['longitude'], _client_time(data)))
    # Retention policy: drop old fixes unless an unresolved alert makes them evidence in a missing-person case.
    if not conn.execute("SELECT 1 FROM Alerts WHERE user_id = ? AND status = 'Active' LIMIT 1", (data['user_id'],)).fetchone():
        conn.execute("DELETE FROM Locations WHERE user_id = ? AND timestamp < datetime('now', ?)",
                     (data['user_id'], f'-{RETENTION_DAYS} days'))
    conn.commit()

    # v2 geofencing: patient may have MULTIPLE named safe zones.
    # Inside ANY zone => safe. Outside ALL zones => count toward an alert.
    zones = conn.execute('SELECT * FROM SafeZones WHERE patient_id = ?', (data['user_id'],)).fetchall()
    if zones:
        pid = data['user_id']
        distances = [(z, haversine_meters(data['latitude'], data['longitude'],
                                          z['center_lat'], z['center_lng'])) for z in zones]
        inside_any = any(d <= z['radius_meters'] for z, d in distances)
        if not inside_any:
            nearest_zone, nearest_d = min(distances, key=lambda x: x[1])
            consecutive_outside_tracker[pid] = consecutive_outside_tracker.get(pid, 0) + 1
            # Fire exactly once per excursion (== 2, no reset) so a patient who stays
            # outside does not generate a new alert every second ping.
            if consecutive_outside_tracker[pid] == 2:
                alert_text = f'Left Safe Zone ({nearest_zone["name"]}, {int(nearest_d)}m away)'
                cur = conn.execute('INSERT INTO Alerts (user_id, type, status) VALUES (?, ?, ?)',
                    (pid, alert_text, 'Active'))
                conn.commit()
                _publish_alert(pid, cur.lastrowid, alert_text)
        else:
            consecutive_outside_tracker[pid] = 0

    conn.close()
    return jsonify({"status": "success", "received": data, "recieved": data  # old misspelt key kept for existing clients
    })


@app.route('/api/latest_location/<int:user_id>')
def latest_location(user_id):
    _audit(user_id, 'viewed live location')
    conn = get_db_connection()
    row = conn.execute('''
        SELECT latitude, longitude, timestamp FROM Locations
        WHERE user_id = ? ORDER BY id DESC LIMIT 1
    ''', (user_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error":"No location recorded yet"}), 404
    return jsonify(dict(row))

@app.route('/api/register_patient', methods=['POST'])
def register_patient():
    data = request.get_json() or {}
    pin = f"{secrets.randbelow(10000):04d}"      # shown once; lets the patient log in on a new device
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO Users (name, age, gender, language, stage, role, secret_hash)
        VALUES (?, ?, ?, ?, ?, 'patient', ?)
    ''', (data.get('name','Patient'), data.get('age'), data.get('gender'),
          data.get('language','English'), data.get('stage','Early'), generate_password_hash(pin)))
    new_id = cursor.lastrowid
    token = _issue_token(conn, new_id, 'patient', 365)
    conn.commit(); conn.close()
    return jsonify({"status":"success", "user_id":new_id, "token":token, "pin":pin})

@app.route('/api/register_caregiver', methods=['POST'])
def register_caregiver():
    data = request.get_json() or {}
    username = str(data.get('username', '')).strip().lower()
    password = str(data.get('password', ''))
    if AUTH_REQUIRED or username:
        if not re.fullmatch(r'[a-z0-9_.]{3,30}', username):
            return bad_request("username must be 3-30 characters: letters, digits, _ or .")
        if len(password) < 6:
            return bad_request("password must be at least 6 characters")
    conn = get_db_connection()
    try:
        cursor = conn.execute("INSERT INTO Users (name, role, username, secret_hash) VALUES (?, 'caregiver', ?, ?)",
                              (data.get('name') or username or 'Caregiver', username or None,
                               generate_password_hash(password) if password else None))
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"status": "error", "message": "that username is taken"}), 409
    new_id = cursor.lastrowid
    token = _issue_token(conn, new_id, 'caregiver', 30)
    conn.commit(); conn.close()
    return jsonify({"status":"success", "user_id":new_id, "token":token})

@app.route('/api/link_caregiver', methods=['POST'])
def link_caregiver():
    data = request.get_json() or {}
    if 'caregiver_id' not in data or 'patient_id' not in data:
        return bad_request("caregiver_id and patient_id are required")
    conn = get_db_connection()
    existing = conn.execute('SELECT id FROM CaregiverLinks WHERE caregiver_id = ? AND patient_id = ?',
        (data['caregiver_id'], data['patient_id'])).fetchone()
    if not existing:
        conn.execute('INSERT INTO CaregiverLinks (caregiver_id, patient_id) VALUES (?, ?)',
            (data['caregiver_id'], data['patient_id']))
        conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/caregiver/<int:caregiver_id>/patients')
def get_linked_patients(caregiver_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT Users.id, Users.name, Users.stage, Users.location_consent
        FROM CaregiverLinks JOIN Users ON Users.id = CaregiverLinks.patient_id
        WHERE CaregiverLinks.caregiver_id = ?
    ''', (caregiver_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/trigger_alert', methods=['POST'])
def trigger_alert():
    data = request.get_json() or {}
    if 'user_id' not in data or not str(data.get('type', '')).strip():
        return bad_request("user_id and type are required")
    conn = get_db_connection()
    cur = conn.execute('INSERT INTO Alerts (user_id, type, status) VALUES (?, ?, ?)',
                 (data['user_id'], str(data['type'])[:120], 'Active'))
    conn.commit(); conn.close()
    _publish_alert(int(data['user_id']), cur.lastrowid, str(data['type'])[:120])
    return jsonify({"status":"success", "alert_id": cur.lastrowid})

@app.route('/api/alerts/<int:user_id>')
def get_alerts(user_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT id, type, status, timestamp, acknowledged_at, resolution FROM Alerts
        WHERE user_id = ? ORDER BY id DESC LIMIT 5
    ''', (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


def haversine_meters(lat1, lng1, lat2, lng2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

@app.route('/api/set_geofence', methods=['POST'])
def set_geofence():
    data = request.get_json() or {}
    # Accept short aliases (lat/lng/radius_m) for robustness.
    if 'center_lat' not in data and 'lat' in data:
        data['center_lat'] = data['lat']
    if 'center_lng' not in data and 'lng' in data:
        data['center_lng'] = data['lng']
    if 'radius_meters' not in data and 'radius_m' in data:
        data['radius_meters'] = data['radius_m']
    missing = [f for f in ('patient_id', 'center_lat', 'center_lng') if f not in data]
    if missing:
        return jsonify({"status": "error", "missing": missing}), 400
    conn = get_db_connection()
    # v2 schema: SafeZones is UNIQUE(patient_id, name); legacy endpoint manages the 'Home' zone.
    conn.execute('''
        INSERT INTO SafeZones (patient_id, name, center_lat, center_lng, radius_meters)
        VALUES (?, 'Home', ?, ?, ?)
        ON CONFLICT(patient_id, name) DO UPDATE SET
            center_lat=excluded.center_lat,
            center_lng=excluded.center_lng,
            radius_meters=excluded.radius_meters,
            updated_at=CURRENT_TIMESTAMP
    ''', (data['patient_id'], data['center_lat'], data['center_lng'], data.get('radius_meters', 200)))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/geofence/<int:patient_id>')
def get_geofence(patient_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM SafeZones WHERE patient_id = ? AND name = 'Home'", (patient_id,)).fetchone()
    if not row:
        row = conn.execute('SELECT * FROM SafeZones WHERE patient_id = ?', (patient_id,)).fetchone()
    conn.close()
    return jsonify(dict(row) if row else None)

@app.route('/api/add_reminder', methods=['POST'])
def add_reminder():
    data = request.get_json() or {}
    # Accept friendly aliases so callers can use {medicine, time} as well.
    if 'title' not in data and 'medicine' in data:
        data['title'] = data['medicine']
    if 'reminder_time' not in data and 'time' in data:
        data['reminder_time'] = data['time']
    missing = [f for f in ('patient_id', 'title', 'reminder_time') if f not in data]
    if missing:
        return jsonify({"status": "error", "missing": missing}), 400
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO Reminders (patient_id, title, reminder_time, repeat_daily)
        VALUES (?, ?, ?, ?)
    ''', (data['patient_id'], data['title'], data['reminder_time'], data.get('repeat_daily', 1)))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/reminders/<int:patient_id>')
def get_reminders(patient_id):
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT * FROM Reminders WHERE patient_id = ? AND active = 1', (patient_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/reminders/<int:reminder_id>', methods=['DELETE'])
def delete_reminder(reminder_id):
    conn = get_db_connection()
    conn.execute('UPDATE Reminders SET active = 0 WHERE id = ?', (reminder_id,))
    conn.commit(); conn.close()
    return jsonify({"status": "deleted"})


# ============================================================
# ENHANCED GEOFENCING — named safe zones + movement history
# ============================================================

@app.route('/api/set_geofence_v2', methods=['POST'])
def set_geofence_v2():
    """Create/update a NAMED safe zone (home, park, temple...). One row per zone."""
    data = request.get_json() or {}
    # Accept short aliases (lat/lng/radius_m) for robustness.
    if 'center_lat' not in data and 'lat' in data:
        data['center_lat'] = data['lat']
    if 'center_lng' not in data and 'lng' in data:
        data['center_lng'] = data['lng']
    if 'radius_meters' not in data and 'radius_m' in data:
        data['radius_meters'] = data['radius_m']
    required = ('patient_id', 'center_lat', 'center_lng')
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"status": "error", "missing": missing}), 400
    name = data.get('name', 'Home')
    try:
        radius = float(data.get('radius_meters', 200))
    except (TypeError, ValueError):
        return bad_request("radius_meters must be a number")
    if not 10 <= radius <= 50000:
        return bad_request("radius_meters must be between 10 and 50000")
    conn = get_db_connection()
    existing = conn.execute(
        'SELECT patient_id FROM SafeZones WHERE patient_id = ? AND name = ?',
        (data['patient_id'], name)).fetchone()
    if existing:
        conn.execute('''UPDATE SafeZones SET center_lat=?, center_lng=?, radius_meters=?,
                        updated_at=CURRENT_TIMESTAMP WHERE patient_id=? AND name=?''',
                     (data['center_lat'], data['center_lng'], radius, data['patient_id'], name))
    else:
        conn.execute('''INSERT INTO SafeZones (patient_id, name, center_lat, center_lng, radius_meters)
                        VALUES (?, ?, ?, ?, ?)''',
                     (data['patient_id'], name, data['center_lat'], data['center_lng'], radius))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "zone": name})


@app.route('/api/geofences/<int:patient_id>')
def get_geofences(patient_id):
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM SafeZones WHERE patient_id = ?', (patient_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/geofence/delete', methods=['POST'])
def delete_geofence():
    data = request.get_json() or {}
    if 'patient_id' not in data or 'name' not in data:
        return bad_request("patient_id and name are required")
    conn = get_db_connection()
    conn.execute('DELETE FROM SafeZones WHERE patient_id = ? AND name = ?',
                 (data['patient_id'], data['name']))
    conn.commit(); conn.close()
    return jsonify({"status": "deleted"})


@app.route('/api/location_history/<int:user_id>')
def location_history(user_id):
    _audit(user_id, 'viewed movement trail')
    """Last N pings for the caregiver's breadcrumb trail on the map."""
    conn = get_db_connection()
    limit = request.args.get('limit', 50, type=int)
    limit = max(1, min(limit if limit is not None else 50, 500))
    rows = conn.execute('''SELECT latitude, longitude, timestamp FROM Locations
                           WHERE user_id = ? ORDER BY id DESC LIMIT ?''', (user_id, limit)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reversed(rows)])


# ============================================================
# AI PERSONALIZATION ENGINE
# Rule-based adaptive difficulty + spaced-repetition seeding.
# (Design for an LLM/ML upgrade is documented in docs/AI_FEATURES.md
#  and RESEARCH_PAPER.md — this endpoint is the drop-in seam.)
# ============================================================


ROUNDS_BY_DIFFICULTY = {'Easy': 3, 'Medium': 6, 'Hard': 8}  # word_picture_match round counts

def _ratio(h):
    """Fraction of the maximum score achieved (0..1), whatever the game's scale."""
    score = h['score'] or 0
    mx = h.get('max_score')
    if not mx:  # older rows: infer from difficulty, else assume a 0-100 scale
        mx = ROUNDS_BY_DIFFICULTY.get(h.get('difficulty')) if h['game_type'] == 'word_picture_match' else None
        if not mx or score > mx:
            mx = 100
    return min(1.0, score / mx)

def _ema(values, alpha=0.4):
    """Exponential moving average — weighs recent sessions more heavily."""
    if not values:
        return None
    e = values[0]
    for v in values[1:]:
        e = alpha * v + (1 - alpha) * e
    return e

@app.route('/api/ai/recommendations/<int:user_id>')
def ai_recommendations(user_id):
    conn = get_db_connection()
    stage_row = conn.execute('SELECT stage FROM Users WHERE id = ?', (user_id,)).fetchone()
    stage = (stage_row['stage'] if stage_row else 'Early') or 'Early'
    sessions = conn.execute('''SELECT game_type, score, max_score, difficulty, timestamp
                               FROM GameSessions WHERE user_id = ?
                               ORDER BY id DESC LIMIT 100''', (user_id,)).fetchall()
    conn.close()

    baseline = STAGE_BASELINE.get(stage, 0.65)
    by_game = {}
    for s in sessions:
        by_game.setdefault(s['game_type'], []).append(dict(s))

    recommendations = []
    for game_type, hist in by_game.items():
        # hist is newest-first; the EMA needs oldest-first so RECENT sessions weigh most.
        chronological = list(reversed(hist[:10]))
        norm_scores = [min(1.0, _ratio(h) / baseline) for h in chronological]
        recent = _ema(norm_scores)
        if recent is None:
            recent = 0.5
        streak = len(hist)
        last_ts = hist[0]['timestamp']

        if recent > 0.8:
            difficulty, rationale = 'Hard', "consistently high recent performance"
        elif recent < 0.4:
            difficulty, rationale = 'Easy', "recent scores dropped below comfort level"
        else:
            difficulty, rationale = 'Medium', "performance is within target band"

        # spaced repetition: nudge games not played recently
        idle_days = 999
        try:
            last_dt = datetime.strptime(last_ts.split('.')[0], '%Y-%m-%d %H:%M:%S')
            idle_days = (datetime.now(timezone.utc).replace(tzinfo=None) - last_dt).days
        except Exception:
            pass
        priority = round(recent * 0.6 + min(idle_days, 7) / 7 * 0.4, 2)

        recommendations.append({
            "game_type": game_type,
            "suggested_difficulty": difficulty,
            "rationale": rationale,
            "times_played": streak,
            "days_since_last_play": idle_days,
            "priority": priority
        })

    recommendations.sort(key=lambda r: -r["priority"])
    return jsonify({
        "user_id": user_id,
        "stage": stage,
        "baseline": baseline,
        "total_sessions": len(sessions),
        "recommendations": recommendations
    })


# =====================================================================
# SECURITY, CONSENT, AUDIT, ALERT WORKFLOW, LIVE PUSH, CLINICAL REPORTS
# =====================================================================
ANY, PATIENT, CAREGIVER = 'any', 'patient', 'caregiver'
OPEN_ENDPOINTS = {'register_patient', 'register_caregiver', 'login'}
# endpoint -> (allowed account type, where to find the patient it concerns)
# Anything not listed here is denied by default once login is required.
POLICY = {
    'save_score': (PATIENT, 'body'), 'update_location': (PATIENT, 'body'),
    'trigger_alert': (PATIENT, 'body'), 'set_stage': (PATIENT, 'body'),
    'set_consent': (PATIENT, None), 'new_link_code': (PATIENT, None), 'erase_my_data': (PATIENT, None),
    'my_caregivers': (PATIENT, None), 'unlink_caregiver': (PATIENT, None), 'access_log': (PATIENT, None),
    'link_with_code': (CAREGIVER, None), 'stream': (CAREGIVER, None),
    'get_linked_patients': (CAREGIVER, 'caregiver_url'),
    'set_geofence': (CAREGIVER, 'body'), 'set_geofence_v2': (CAREGIVER, 'body'),
    'delete_geofence': (CAREGIVER, 'body'), 'add_reminder': (CAREGIVER, 'body'), 'add_moca': (CAREGIVER, 'body'),
    'delete_reminder': (CAREGIVER, 'reminder'), 'acknowledge_alert': (CAREGIVER, 'alert'),
    'get_progress': (ANY, 'url'), 'latest_location': (ANY, 'url'), 'location_history': (ANY, 'url'),
    'get_alerts': (ANY, 'url'), 'get_geofence': (ANY, 'url'), 'get_geofences': (ANY, 'url'),
    'get_reminders': (ANY, 'url'), 'ai_recommendations': (ANY, 'url'), 'metrics': (ANY, 'url'),
    'clinical': (ANY, 'url'), 'report': (ANY, 'url'),
    'link_caregiver': (None, None),   # legacy "link by raw ID" - replaced by one-time link codes
}

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _ts(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def _parse_ts(s):
    return datetime.strptime(str(s).split('.')[0][:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')

def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def _client_time(data):
    """Offline clients send recorded_at so queued pings/scores keep their real time."""
    raw = data.get('recorded_at')
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None
    now = _now()
    if dt > now + timedelta(minutes=5) or dt < now - timedelta(days=7):
        return None
    return _ts(dt)

def _issue_token(conn, user_id, role, days):
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO Sessions (token, user_id, role, expires_at) VALUES (?, ?, ?, ?)',
                 (token, user_id, role, _ts(_now() + timedelta(days=days))))
    return token

def _identity():
    header = request.headers.get('Authorization', '')
    token = header[7:] if header.startswith('Bearer ') else request.args.get('token')
    if not token:
        return None
    conn = get_db_connection()
    row = conn.execute('SELECT user_id, role FROM Sessions WHERE token = ? AND expires_at > ?',
                       (token, _ts(_now()))).fetchone()
    conn.close()
    return (row['user_id'], row['role']) if row else None

_attempts = {}
def _too_many(key, limit, window):
    now = time.time()
    hits = [t for t in _attempts.get(key, []) if now - t < window] + [now]
    _attempts[key] = hits
    return len(hits) > limit

def _is_linked(caregiver_id, patient_id):
    conn = get_db_connection()
    row = conn.execute('SELECT 1 FROM CaregiverLinks WHERE caregiver_id = ? AND patient_id = ?',
                       (caregiver_id, patient_id)).fetchone()
    conn.close()
    return row is not None

def _target_patient(how):
    view = request.view_args or {}
    if how == 'url':
        return _as_int(view.get('user_id', view.get('patient_id')))
    if how == 'body':
        body = request.get_json(silent=True) or {}
        return _as_int(body.get('user_id', body.get('patient_id')))
    if how in ('reminder', 'alert'):
        conn = get_db_connection()
        if how == 'reminder':
            row = conn.execute('SELECT patient_id AS p FROM Reminders WHERE id = ?', (view.get('reminder_id'),)).fetchone()
        else:
            row = conn.execute('SELECT user_id AS p FROM Alerts WHERE id = ?', (view.get('alert_id'),)).fetchone()
        conn.close()
        return row['p'] if row else None
    return None

def _deny(message, code=403):
    return jsonify({"status": "error", "message": message}), code

@app.before_request
def auth_gate():
    if not AUTH_REQUIRED or request.method == 'OPTIONS' or not request.path.startswith('/api/'):
        return None
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    ident = _identity()
    if not ident:
        return _deny("login required", 401)
    g.uid, g.role = ident
    policy = POLICY.get(request.endpoint)
    if not policy or policy[0] is None:
        return _deny("this endpoint is disabled (caregivers connect with a one-time link code)")
    role, how = policy
    if role != ANY and g.role != role:
        return _deny("this action needs a %s account" % role)
    if how is None:
        return None
    if how == 'caregiver_url':
        return None if (request.view_args or {}).get('caregiver_id') == g.uid else _deny("not your account")
    target = _target_patient(how)
    if target is None:
        if how in ('reminder', 'alert'):
            return _deny("not found", 404)
        if g.role == 'patient' and how == 'body':
            return None  # body omitted its id; the endpoint's own validation reports it
        return _deny("patient id required", 400)
    allowed = (target == g.uid) if g.role == 'patient' else _is_linked(g.uid, target)
    return None if allowed else _deny("you are not allowed to access this patient")

def _audit(patient_id, action, caregiver_id=None):
    """Audit trail the patient can read: who looked at their data, and when."""
    caregiver_id = caregiver_id or (g.uid if getattr(g, 'role', None) == 'caregiver' else None)
    if caregiver_id is None:
        return
    conn = get_db_connection()
    recent = conn.execute("SELECT 1 FROM AccessLog WHERE patient_id = ? AND caregiver_id = ? AND action = ? "
                          "AND timestamp > datetime('now', '-5 minutes')", (patient_id, caregiver_id, action)).fetchone()
    if not recent:  # the dashboard polls every few seconds; log one entry per 5 minutes
        conn.execute('INSERT INTO AccessLog (patient_id, caregiver_id, action) VALUES (?, ?, ?)',
                     (patient_id, caregiver_id, action))
        conn.commit()
    conn.close()

def _need_login():
    uid = getattr(g, 'uid', None)
    return uid, (None if uid is not None else bad_request("login required (the server runs with MANOVA_AUTH=off)"))

# ---------- login ----------
@app.route('/api/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    secret = str(d.get('secret', ''))
    who = str(d.get('username') or d.get('user_id') or '')
    if _too_many(f"login:{request.remote_addr}:{who}", 8, 600):
        return _deny("too many attempts, try again in a few minutes", 429)
    conn = get_db_connection()
    if d.get('username'):
        row = conn.execute("SELECT id, role, secret_hash FROM Users WHERE username = ?",
                           (str(d['username']).strip().lower(),)).fetchone()
    else:
        row = conn.execute("SELECT id, role, secret_hash FROM Users WHERE id = ? AND role = 'patient'",
                           (_as_int(d.get('user_id')),)).fetchone()
    if not row or not row['secret_hash'] or not check_password_hash(row['secret_hash'], secret):
        conn.close()
        return _deny("invalid credentials", 401)
    token = _issue_token(conn, row['id'], row['role'], 365 if row['role'] == 'patient' else 30)
    conn.commit(); conn.close()
    return jsonify({"status": "success", "user_id": row['id'], "role": row['role'], "token": token})

# ---------- consent, linking, audit, erasure ----------
@app.route('/api/consent', methods=['POST'])
def set_consent():
    uid, err = _need_login()
    if err: return err
    allowed = 1 if (request.get_json(silent=True) or {}).get('allowed') else 0
    conn = get_db_connection()
    before = conn.execute('SELECT location_consent FROM Users WHERE id = ?', (uid,)).fetchone()
    conn.execute('UPDATE Users SET location_consent = ? WHERE id = ?', (allowed, uid))
    if before and int(before['location_consent'] or 0) != allowed:
        conn.execute('INSERT INTO AccessLog (patient_id, caregiver_id, action) VALUES (?, NULL, ?)',
                     (uid, 'you turned location sharing ' + ('on' if allowed else 'off')))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "location_consent": bool(allowed)})

@app.route('/api/link_code', methods=['POST'])
def new_link_code():
    uid, err = _need_login()
    if err: return err
    code = f"{secrets.randbelow(10**6):06d}"
    conn = get_db_connection()
    conn.execute('UPDATE Users SET link_code = ?, link_expires = ? WHERE id = ?',
                 (code, _ts(_now() + timedelta(minutes=10)), uid))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "code": code, "expires_in_minutes": 10})

@app.route('/api/link_with_code', methods=['POST'])
def link_with_code():
    uid, err = _need_login()
    if err: return err
    if _too_many(f"link:{uid}", 10, 600):
        return _deny("too many attempts, try again in a few minutes", 429)
    code = str((request.get_json(silent=True) or {}).get('code', '')).strip()
    conn = get_db_connection()
    patient = conn.execute("SELECT id, name FROM Users WHERE role = 'patient' AND link_code = ? AND link_expires > ?",
                           (code, _ts(_now()))).fetchone() if code else None
    if not patient:
        conn.close()
        return _deny("invalid or expired code", 404)
    if not conn.execute('SELECT 1 FROM CaregiverLinks WHERE caregiver_id = ? AND patient_id = ?', (uid, patient['id'])).fetchone():
        conn.execute('INSERT INTO CaregiverLinks (caregiver_id, patient_id) VALUES (?, ?)', (uid, patient['id']))
    conn.execute('UPDATE Users SET link_code = NULL, link_expires = NULL WHERE id = ?', (patient['id'],))
    conn.commit(); conn.close()
    _audit(patient['id'], 'was connected as a caregiver', caregiver_id=uid)
    return jsonify({"status": "success", "patient_id": patient['id'], "patient_name": patient['name']})

@app.route('/api/my_caregivers')
def my_caregivers():
    uid, err = _need_login()
    if err: return err
    conn = get_db_connection()
    rows = conn.execute('SELECT Users.id, Users.name FROM CaregiverLinks JOIN Users ON Users.id = CaregiverLinks.caregiver_id '
                        'WHERE CaregiverLinks.patient_id = ?', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/unlink_caregiver', methods=['POST'])
def unlink_caregiver():
    uid, err = _need_login()
    if err: return err
    cid = _as_int((request.get_json(silent=True) or {}).get('caregiver_id'))
    conn = get_db_connection()
    conn.execute('DELETE FROM CaregiverLinks WHERE caregiver_id = ? AND patient_id = ?', (cid, uid))
    conn.execute('INSERT INTO AccessLog (patient_id, caregiver_id, action) VALUES (?, ?, ?)',
                 (uid, cid, 'access was removed by you'))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/access_log')
def access_log():
    uid, err = _need_login()
    if err: return err
    conn = get_db_connection()
    rows = conn.execute('SELECT AccessLog.action, AccessLog.timestamp, Users.name AS caregiver FROM AccessLog '
                        'LEFT JOIN Users ON Users.id = AccessLog.caregiver_id WHERE AccessLog.patient_id = ? '
                        'ORDER BY AccessLog.id DESC LIMIT 30', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/erase_my_data', methods=['POST'])
def erase_my_data():
    uid, err = _need_login()
    if err: return err
    scope = (request.get_json(silent=True) or {}).get('scope', 'locations')
    conn = get_db_connection()
    deleted = {"locations": conn.execute('DELETE FROM Locations WHERE user_id = ?', (uid,)).rowcount}
    if scope == 'all':
        for table, col in (('GameSessions', 'user_id'), ('Alerts', 'user_id'), ('Reminders', 'patient_id'),
                           ('SafeZones', 'patient_id'), ('CaregiverLinks', 'patient_id'),
                           ('AccessLog', 'patient_id'), ('ClinicalScores', 'patient_id'), ('Sessions', 'user_id')):
            deleted[table] = conn.execute(f'DELETE FROM {table} WHERE {col} = ?', (uid,)).rowcount
        conn.execute('DELETE FROM Users WHERE id = ?', (uid,))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "deleted": deleted})

# ---------- alert workflow + metrics ----------
@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    d = request.get_json(silent=True) or {}
    resolution = d.get('resolution', 'resolved')
    if resolution not in ('resolved', 'false_alarm'):
        return bad_request("resolution must be 'resolved' or 'false_alarm'")
    conn = get_db_connection()
    cur = conn.execute("UPDATE Alerts SET status = 'Acknowledged', acknowledged_at = CURRENT_TIMESTAMP, "
                       "acknowledged_by = ?, resolution = ? WHERE id = ? AND acknowledged_at IS NULL",
                       (getattr(g, 'uid', None), resolution, alert_id))
    conn.commit(); conn.close()
    return jsonify({"status": "success", "updated": cur.rowcount})

@app.route('/api/metrics/<int:patient_id>')
def metrics(patient_id):
    conn = get_db_connection()
    rows = conn.execute('SELECT type, timestamp, acknowledged_at, resolution FROM Alerts WHERE user_id = ?', (patient_id,)).fetchall()
    conn.close()
    times = [(_parse_ts(r['acknowledged_at']) - _parse_ts(r['timestamp'])).total_seconds() for r in rows if r['acknowledged_at']]
    first = min((_parse_ts(r['timestamp']) for r in rows), default=_now())
    days = max(1, (_now() - first).days + 1)
    false_alarms = sum(1 for r in rows if r['resolution'] == 'false_alarm')
    return jsonify({
        "alerts_total": len(rows),
        "geofence_alerts": sum(1 for r in rows if r['type'].startswith('Left Safe Zone')),
        "sos_alerts": sum(1 for r in rows if not r['type'].startswith('Left Safe Zone')),
        "acknowledged": len(times), "false_alarms": false_alarms,
        "false_alarms_per_day": round(false_alarms / days, 2),
        "median_response_seconds": round(statistics.median(times), 1) if times else None})

# ---------- live push (Server-Sent Events) ----------
_subscribers = {}
_sub_lock = threading.Lock()

def _publish_alert(patient_id, alert_id, alert_type):
    conn = get_db_connection()
    caregivers = [r['caregiver_id'] for r in conn.execute('SELECT caregiver_id FROM CaregiverLinks WHERE patient_id = ?', (patient_id,))]
    name = conn.execute('SELECT name FROM Users WHERE id = ?', (patient_id,)).fetchone()
    conn.close()
    payload = json.dumps({"alert_id": alert_id, "patient_id": patient_id,
                          "patient_name": name['name'] if name else 'Patient', "type": alert_type})
    with _sub_lock:
        for cid in caregivers:
            for q in _subscribers.get(cid, ()):
                q.put(payload)

@app.route('/api/stream')
def stream():
    cid = getattr(g, 'uid', None) or request.args.get('caregiver_id', type=int)
    if cid is None:
        return bad_request("caregiver_id required")
    q = queue.Queue()
    with _sub_lock:
        _subscribers.setdefault(cid, set()).add(q)
    def events():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    yield f"event: alert\ndata: {q.get(timeout=20)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sub_lock:
                _subscribers.get(cid, set()).discard(q)
    return Response(stream_with_context(events()), mimetype='text/event-stream',
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ---------- clinical: MoCA, trends, printable report ----------
def _clinical_summary(conn, pid):
    base = conn.execute('SELECT name, age, stage FROM Users WHERE id = ?', (pid,)).fetchone()
    sessions = [dict(r) for r in conn.execute('SELECT game_type, score, max_score, difficulty, timestamp FROM GameSessions '
                                              'WHERE user_id = ? ORDER BY id', (pid,))]
    for s in sessions:
        s['_ratio'], s['_dt'] = _ratio(s), _parse_ts(s['timestamp'])
    weeks = defaultdict(list)
    for s in sessions:
        year, week, _ = s['_dt'].isocalendar()
        weeks[(f"{year}-W{week:02d}", s['game_type'])].append(s['_ratio'])
    weekly = [{"week": k[0], "game": k[1], "mean_ratio": round(sum(v) / len(v), 2), "n": len(v)} for k, v in sorted(weeks.items())]
    now = _now()
    recent = [s['_ratio'] for s in sessions if s['_dt'] >= now - timedelta(days=14)]
    prior = [s['_ratio'] for s in sessions if now - timedelta(days=28) <= s['_dt'] < now - timedelta(days=14)]
    decline = len(recent) >= 3 and len(prior) >= 3 and (sum(prior) / len(prior) - sum(recent) / len(recent)) >= 0.15
    moca = [dict(r) for r in conn.execute('SELECT moca_score, assessed_on FROM ClinicalScores WHERE patient_id = ? ORDER BY assessed_on', (pid,))]
    xs, ys = [], []
    for m in moca:
        try:
            end = datetime.strptime(m['assessed_on'], '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            continue
        window = [s['_ratio'] for s in sessions if end - timedelta(days=31) < s['_dt'] <= end]
        if len(window) >= 2:
            xs.append(m['moca_score']); ys.append(sum(window) / len(window))
    corr = None
    if len(xs) >= 3:
        try:
            corr = round(statistics.correlation(xs, ys), 2)
        except statistics.StatisticsError:
            corr = None
    return {"patient": dict(base) if base else {}, "sessions": len(sessions), "weekly": weekly, "moca": moca,
            "moca_vs_games_correlation": corr, "moca_pairs": len(xs), "decline_flag": decline,
            "nudge": ("Game performance over the last 2 weeks is clearly lower than the 2 weeks before. "
                      "This is not a diagnosis - consider discussing it with the patient's neurologist.") if decline else None}

@app.route('/api/clinical/<int:patient_id>')
def clinical(patient_id):
    conn = get_db_connection()
    out = _clinical_summary(conn, patient_id)
    conn.close()
    return jsonify(out)

@app.route('/api/moca', methods=['POST'])
def add_moca():
    d = request.get_json(silent=True) or {}
    score = _as_int(d.get('score'))
    date = str(d.get('date') or _now().strftime('%Y-%m-%d'))
    if score is None or not 0 <= score <= 30:
        return bad_request("score must be a whole number from 0 to 30")
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return bad_request("date must look like 2026-11-01")
    conn = get_db_connection()
    conn.execute('INSERT INTO ClinicalScores (patient_id, moca_score, assessed_on, entered_by) VALUES (?, ?, ?, ?)',
                 (_as_int(d.get('patient_id')), score, date, getattr(g, 'uid', None)))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/report/<int:patient_id>')
def report(patient_id):
    _audit(patient_id, 'opened the clinician report')
    conn = get_db_connection()
    c = _clinical_summary(conn, patient_id)
    conn.close()
    e = _html.escape
    p = c['patient']
    weekly = "".join(f"<tr><td>{e(w['week'])}</td><td>{e(w['game'])}</td><td>{int(w['mean_ratio'] * 100)}%</td><td>{w['n']}</td></tr>" for w in c['weekly']) \
        or "<tr><td colspan=4>No game sessions yet.</td></tr>"
    moca = "".join(f"<tr><td>{e(str(m['assessed_on']))}</td><td>{m['moca_score']} / 30</td></tr>" for m in c['moca']) \
        or "<tr><td colspan=2>No MoCA scores entered.</td></tr>"
    corr = (f"{c['moca_vs_games_correlation']} (n = {c['moca_pairs']} assessments)" if c['moca_vs_games_correlation'] is not None
            else "not enough paired data yet (needs 3 or more MoCA entries with game sessions around them)")
    nudge = f"<div class=nudge>{e(c['nudge'])}</div>" if c['nudge'] else ""
    page = f"""<!DOCTYPE html><html><head><meta charset=utf-8><title>Manova clinician report</title>
<style>body{{font-family:Arial,sans-serif;max-width:800px;margin:30px auto;color:#222;padding:0 16px}}h1{{color:#1f5f5b}}
table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}td,th{{border:1px solid #ccc;padding:6px 10px;text-align:left}}th{{background:#eef4f3}}
.nudge{{background:#fff4e0;border-left:5px solid #f5a623;padding:12px;margin:16px 0}}.note{{color:#666;font-size:13px}}
button{{padding:10px 18px;font-size:15px}}@media print{{button{{display:none}}}}</style></head><body>
<h1>Manova - cognitive engagement report</h1>
<p><b>{e(str(p.get('name', 'Patient')))}</b> &middot; age {e(str(p.get('age') or '-'))} &middot; stage {e(str(p.get('stage') or '-'))}
&middot; generated {_now().strftime('%d %b %Y')}</p>
<button onclick="window.print()">Print / Save as PDF</button>{nudge}
<h2>Weekly game performance</h2><p class=note>Share of the maximum score achieved, per game and ISO week.</p>
<table><tr><th>Week</th><th>Game</th><th>Mean score</th><th>Sessions</th></tr>{weekly}</table>
<h2>MoCA assessments (entered by caregiver/clinician)</h2><table><tr><th>Date</th><th>Score</th></tr>{moca}</table>
<p><b>Correlation of MoCA with game performance:</b> {e(corr)}</p>
<p class=note>Game scores are an engagement and trend signal, not a diagnostic test. This report supports, and never replaces,
clinical judgement.</p></body></html>"""
    return Response(page, mimetype='text/html')


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', host='127.0.0.1', port=5000)