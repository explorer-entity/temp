# GEOFENCING & INDIVIDUAL TRACKING — Design

## Problem
Dementia patients wander (wandering occurs in ~60% of patients) often without recall of how to return home. A single circular "safe zone" is too coarse: patients have several meaningful places (home, temple, market, park).

## What we implemented (v2)
1. **Multiple named safe zones per patient** — `SafeZones(patient_id, name, center_lat, center_lng, radius_meters)` with `UNIQUE(patient_id, name)`. Legacy v1 tables are auto-migrated by `setup_db.py` (adds `name DEFAULT 'Home'`).
2. **Zone-membership logic** — on every `/api/update_location` ping the server computes Haversine distance to *every* zone. Inside ANY zone ⇒ safe & counter reset. Outside ALL zones ⇒ consecutive counter++; after **2 consecutive outside pings** an alert is created whose text names the nearest zone and distance, e.g. `Left Safe Zone (Temple, 74741m away)`. The debounce prevents GPS-jitter false alarms.
3. **Movement history/trail** — all pings stored in `Locations`; `GET /api/location_history/<id>?limit=50` returns them chronologically; the caregiver map draws a dashed breadcrumb polyline so caregivers can see *where the patient has been*, not just where they are.
4. **Caregiver UX** — create/update zones by name at the last known location, view all circles with popups, delete zones, status line listing active zones.
5. **Consent gate** — the patient profile screen requires an explicit "Allow Location" action before any ping leaves the device.

## Known limitations → roadmap (docs/ROADMAP.md)
- In-memory breach counter (lost on restart) → persist `outside_streak` in DB.
- Browser polling model → native apps with OS-level geofence APIs (Android GeofencingClient / iOS CLCircularRegion) for low-battery background monitoring.
- No schedule-based zones (e.g., temple only safe 7–9 am).
- No reverse-geocoded human-readable place names in alerts.
