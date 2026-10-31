from flask import Flask, jsonify, request
import sqlite3
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def get_db_connection():
    conn = sqlite3.connect("smriti.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return "Hello, Nexus Prime!"

@app.route('/api/set_stage', methods=['POST'])
def set_stage():
    data = request.get_json() or {}
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
        INSERT INTO GameSessions (user_id, game_type, score, difficulty)
        VALUES (?, ?, ?, ?)
    ''', (int(data['user_id']), data['game_type'], int(data['score']), data.get('difficulty', 'Easy')))
    conn.commit(); conn.close()
    return jsonify({"status":"success", "message":"Score saved to database"})

@app.route('/api/progress/<int:user_id>')
def get_progress(user_id):
    conn = get_db_connection()

    rows = conn.execute('''
        SELECT game_type, score, difficulty, timestamp
        FROM GameSessions
        WHERE user_id = ?
        ORDER BY timestamp DESC
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
    conn = get_db_connection()
    conn.execute('INSERT INTO Locations (user_id, latitude, longitude) VALUES (?, ?, ?)',
        (data['user_id'], data['latitude'], data['longitude']))
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
            if consecutive_outside_tracker[pid] >= 2:
                conn.execute('INSERT INTO Alerts (user_id, type, status) VALUES (?, ?, ?)',
                    (pid, f'Left Safe Zone ({nearest_zone["name"]}, {int(nearest_d)}m away)', 'Active'))
                conn.commit()
                consecutive_outside_tracker[pid] = 0
        else:
            consecutive_outside_tracker[pid] = 0

    conn.close()
    return jsonify({"status": "success", "recieved": data})


@app.route('/api/latest_location/<int:user_id>')
def latest_location(user_id):
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
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO Users (name, age, gender, language, stage, role)
        VALUES (?, ?, ?, ?, ?, 'patient')
    ''', (data.get('name','Patient'), data.get('age'), data.get('gender'),
          data.get('language','English'), data.get('stage','Early')))
    new_id = cursor.lastrowid
    conn.commit(); conn.close()
    return jsonify({"status":"success", "user_id":new_id})

@app.route('/api/register_caregiver', methods=['POST'])
def register_caregiver():
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.execute("INSERT INTO Users (name, role) VALUES (?, 'caregiver')", (data.get('name','Caregiver'),))
    new_id = cursor.lastrowid
    conn.commit(); conn.close()
    return jsonify({"status":"success", "user_id":new_id})

@app.route('/api/link_caregiver', methods=['POST'])
def link_caregiver():
    data = request.get_json() or {}
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
        SELECT Users.id, Users.name, Users.stage
        FROM CaregiverLinks JOIN Users ON Users.id = CaregiverLinks.patient_id
        WHERE CaregiverLinks.caregiver_id = ?
    ''', (caregiver_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/trigger_alert', methods=['POST'])
def trigger_alert():
    data = request.get_json() or {}
    conn = get_db_connection()
    conn.execute('INSERT INTO Alerts (user_id, type, status) VALUES (?, ?, ?)',
                 (data['user_id'], data['type'], 'Active'))
    conn.commit(); conn.close()
    return jsonify({"status":"success"})

@app.route('/api/alerts/<int:user_id>')
def get_alerts(user_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT type, status, timestamp FROM Alerts
        WHERE user_id = ? ORDER BY id DESC LIMIT 5
    ''', (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


import math

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
    radius = float(data.get('radius_meters', 200))
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
    conn = get_db_connection()
    conn.execute('DELETE FROM SafeZones WHERE patient_id = ? AND name = ?',
                 (data['patient_id'], data['name']))
    conn.commit(); conn.close()
    return jsonify({"status": "deleted"})


@app.route('/api/location_history/<int:user_id>')
def location_history(user_id):
    """Last N pings for the caregiver's breadcrumb trail on the map."""
    conn = get_db_connection()
    limit = int(request.args.get('limit', 50))
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

STAGE_BASELINE = {'Early': 0.85, 'Moderate': 0.65, 'Severe': 0.45}

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
    sessions = conn.execute('''SELECT game_type, score, difficulty, timestamp
                               FROM GameSessions WHERE user_id = ?
                               ORDER BY timestamp DESC LIMIT 100''', (user_id,)).fetchall()
    conn.close()

    baseline = STAGE_BASELINE.get(stage, 0.65)
    by_game = {}
    for s in sessions:
        by_game.setdefault(s['game_type'], []).append(dict(s))

    recommendations = []
    for game_type, hist in by_game.items():
        # normalise score against the stage baseline so scores are comparable
        norm_scores = [min(1.0, (h['score'] or 0) / max(1, 100 * baseline)) for h in hist]
        recent = _ema(norm_scores[:10]) or 0.5
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
            from datetime import datetime
            last_dt = datetime.strptime(last_ts.split('.')[0], '%Y-%m-%d %H:%M:%S')
            idle_days = (datetime.utcnow() - last_dt).days
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


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
