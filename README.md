# Nexus Prime (Manova) — SIH 2026 (SIH26003)

Companion ecosystem for elderly dementia patients in India's North-Eastern Region:
cognitive games with **AI personalization**, a voice assistant (Smriti), GPS safety with
**multi-zone geofencing & movement tracking**, and a **dedicated caregiver app/dashboard**.

## What each part of the system does
| Component | File | Purpose |
|---|---|---|
| Patient app (PWA) | `static/home.html` | Large-button home, games hub, progress screen, family/SOS, profile with location consent, live map + periodic GPS pings, daily reminders with voice + push notifications, multi-language UI (English/Hindi/Bengali/Assamese) |
| Game — Word Picture Match | `static/games/word_picture_match.html` | Naming/recognition drill. Now **AI-tuned**: fetches `/api/ai/recommendations/<id>` to set round count, option-set size and shuffled distractors |
| Game — Story Detective | `static/games/story_detective.html` | Reading-comprehension game with adaptive difficulty ladder; now **starts at the AI-recommended level** instead of always Easy |
| Voice assistant demo | `static/ask-smriti-demo.html` | Web Speech API (STT + TTS) Q&A helper for the patient |
| Caregiver app | `static/caregiver-dashboard.html` | Register/link patients, live Leaflet map, **multiple named safe zones (Home/Temple/Park)**, breadcrumb movement trail (`/api/location_history`), SOS + geofence alerts, reminders, cognitive progress |
| Backend | `app.py` | Flask REST API over SQLite (auth-free demo tier) |
| Database | `setup_db.py` | Schema creation + legacy-safe migrations (SafeZones v2) |

## Tech Stack
- Frontend: HTML, CSS, JavaScript (PWA: `manifest.json` + `sw.js`)
- Backend: Python (Flask) + SQLite
- Voice: Web Speech API · Maps: Leaflet.js + OpenStreetMap
- AI: rule-based adaptive engine (EMA performance model + spaced repetition); LLM upgrade path documented in `docs/AI_FEATURES.md`

## Setup (do this once, after cloning)
1. `pip install -r requirements.txt`
2. `python setup_db.py` — creates/migrates your local database
3. `python app.py` — starts the server
4. Patient app: `http://localhost:5000/static/home.html`
5. Caregiver app: `http://localhost:5000/static/caregiver-dashboard.html`

## API Reference (backend endpoints)
### Users & linkage
- `POST /api/register_patient` · `POST /api/register_caregiver` · `POST /api/link_caregiver`
- `GET /api/caregiver/<cid>/patients`
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

### Alerts & reminders
- `POST /api/trigger_alert` (incl. "Lost My Way" SOS) · `GET /api/alerts/<user_id>`
- `POST /api/add_reminder` · `GET /api/reminders/<patient_id>` · `DELETE /api/reminders/<id>`

## Documentation
- `RESEARCH_PAPER.md` — full research paper (problem, prior work, architecture, AI design, ethics, evaluation plan)
- `docs/FEATURES.md` — what every component does, feature-by-feature
- `docs/AI_FEATURES.md` — AI personalization: current implementation + LLM/ML roadmap
- `docs/GEOFENCING.md` — geofencing & tracking design
- `docs/ROADMAP.md` — other needed changes (auth, privacy/DPDP compliance, native apps, offline sync…)

## Team Workflow
- Before starting work: `git pull`
- After finishing something: `git add .` → `git commit -m "message"` → `git push`
- Message the group before editing a file someone else likely owns
