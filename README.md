# Nexus Prime (Manova) — SIH 2026 (SIH26003)

Companion ecosystem for elderly dementia patients in India's North-Eastern Region:
cognitive games with **AI personalization**, a voice assistant (Smriti), GPS safety with
**multi-zone geofencing & movement tracking**, and a **dedicated caregiver app/dashboard** with login, consent-based linking, live alerts and clinician reports.

## What each part of the system does
| Component | File | Purpose |
|---|---|---|
| Patient app (PWA) | `static/home.html` | Large-button home, games hub, progress screen, family/SOS, profile with location consent, live map + periodic GPS pings, daily reminders with voice + push notifications, multi-language UI (English/Hindi/Bengali/Assamese) |
| Game — Word Picture Match | `static/games/word_picture_match.html` | Naming/recognition drill. Now **AI-tuned**: fetches `/api/ai/recommendations/<id>` to set round count, option-set size and shuffled distractors |
| Game — Story Detective | `static/games/story_detective.html` | Reading-comprehension game with adaptive difficulty ladder; now **starts at the AI-recommended level** instead of always Easy |
| Voice assistant demo | `static/ask-smriti-demo.html` | Web Speech API (STT + TTS) Q&A helper for the patient |
| Caregiver app | `static/caregiver-dashboard.html` | Register/link patients, live Leaflet map, **multiple named safe zones (Home/Temple/Park)**, breadcrumb movement trail (`/api/location_history`), SOS + geofence alerts, reminders, cognitive progress |
| Shared client | `static/common.js` | Adds the login token to API calls; offline outbox that re-sends scores, pings and SOS alerts when the network returns |
| Backend | `app.py` | Flask REST API over SQLite: login + per-patient authorisation, consent, audit log, live push (SSE), clinical report |
| Database | `setup_db.py` | Schema creation + legacy-safe migrations; `app.py` runs it automatically at start |

## Tech Stack
- Frontend: HTML, CSS, JavaScript (PWA: `manifest.json` + `sw.js`)
- Backend: Python (Flask) + SQLite
- Voice: Web Speech API · Maps: Leaflet.js + OpenStreetMap
- AI: rule-based adaptive engine (EMA performance model + spaced repetition); LLM upgrade path documented in `docs/AI_FEATURES.md`

## Setup (do this once, after cloning)
1. `pip install -r requirements.txt`
2. `python app.py` — starts the server (creates/migrates `smriti.db` itself; `python setup_db.py` still works on its own)
3. Patient app: `http://localhost:5000/static/home.html` — save your profile; note the **Patient ID and 4-digit PIN**
4. Caregiver app: `http://localhost:5000/static/caregiver-dashboard.html` — create an account, then enter the **6-digit link code** from the patient's Profile → *Give a caregiver access*

Environment variables: `MANOVA_AUTH=off` (old open demo mode, no login), `LOCATION_RETENTION_DAYS` (default 30), `FLASK_DEBUG=1`.

## API Reference (backend endpoints)
### Accounts, consent & privacy
- `POST /api/register_patient` (returns token + PIN) · `POST /api/register_caregiver` (username + password) · `POST /api/login`
- Every other `/api/` call needs `Authorization: Bearer <token>`; patients reach only their own data, caregivers only linked patients
- `POST /api/link_code` (patient) → one-time 6-digit code · `POST /api/link_with_code` (caregiver) · `GET /api/my_caregivers` · `POST /api/unlink_caregiver`
- `POST /api/consent` — server-side location consent; pings are refused (403) without it
- `GET /api/access_log` — who viewed the patient's data and when
- `POST /api/erase_my_data` `{scope: locations|all}` — erasure; old pings are also auto-pruned after `LOCATION_RETENTION_DAYS` (unless an alert is active)
- `GET /api/caregiver/<cid>/patients` · `POST /api/set_stage` · `GET /api/get_stage/<user_id>` · legacy `POST /api/link_caregiver` is disabled while auth is on
- `POST /api/set_stage` · `GET /api/get_stage/<user_id>`

### Games & AI personalization
- `POST /api/save_score` — save a game result (now records the AI difficulty actually played)
- `GET /api/progress/<user_id>` — game history
- `GET /api/ai/recommendations/<user_id>` — **NEW**: stage-normalised EMA model → suggested difficulty per game, rationale, idle days, priority ranking

### Geofencing & tracking
- `POST /api/update_location` — ping; checks against **ALL** named zones, alert only if outside every zone (≥2 consecutive pings)
- `POST /api/set_geofence_v2` — **NEW**: create/update a *named* safe zone `{patient_id, name, center_lat, center_lng, radius_meters}`
- `GET /api/geofences/<patient_id>` — **NEW**: list all zones
- `POST /api/geofence/delete` — **NEW**: remove one zone by name
- `GET /api/location_history/<user_id>?limit=50` — **NEW**: breadcrumb trail
- `GET /api/latest_location/<user_id>` · legacy `POST /api/set_geofence`, `GET /api/geofence/<pid>` still work

### Alerts, live push & reminders
- `POST /api/trigger_alert` (incl. "Lost My Way" SOS) · `GET /api/alerts/<user_id>` · `POST /api/alerts/<id>/acknowledge` `{resolution: resolved|false_alarm}` · `GET /api/metrics/<patient_id>` (median response time, false alarms)
- `GET /api/stream?token=…` — Server-Sent Events: caregivers get alerts instantly (the dashboard slows its polling while connected)
- `POST /api/add_reminder` · `GET /api/reminders/<patient_id>` · `DELETE /api/reminders/<id>`

### Clinical
- `POST /api/moca` `{patient_id, score 0-30, date}` · `GET /api/clinical/<patient_id>` (weekly trend, MoCA vs game correlation, decline nudge) · `GET /api/report/<patient_id>` (printable page → Print / Save as PDF)

### Offline
Scores, location pings and SOS alerts that cannot be sent are queued on the device with their real timestamp and re-sent automatically. If an SOS cannot reach the server, the app offers to send it by SMS to the first saved family contact.

## Documentation
- `RESEARCH_PAPER.md` — full research paper (problem, prior work, architecture, AI design, ethics, evaluation plan)
- `docs/FEATURES.md` — what every component does, feature-by-feature
- `docs/AI_FEATURES.md` — AI personalization: current implementation + LLM/ML roadmap
- `docs/GEOFENCING.md` — geofencing & tracking design
- `docs/ROADMAP.md` — what is done and what is still open
- `docs/NATIVE_APPS.md` — plan for background geofencing and true push (not built yet)

## Team Workflow
- Before starting work: `git pull`
- After finishing something: `git add .` → `git commit -m "message"` → `git push`
- Message the group before editing a file someone else likely owns