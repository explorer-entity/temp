# Nexus Prime — SIH 2026 (SIH26003)

Companion app for elderly dementia patients in India's North-Eastern Region — cognitive games, a voice assistant, GPS safety, geofencing support and caregiver connectivity.

## Tech Stack
- Frontend: HTML, CSS, JavaScript
- Backend: Python (Flask)
- Database: SQLite
- Voice: Web Speech API
- Maps: Leaflet.js + OpenStreetMap

## Setup (do this once, after cloning)
1. `pip install -r requirements.txt`
2. `python setup_db.py` — creates your local database
3. `python app.py` — starts the server
4. Open `http://localhost:5000` in your browser

## API Reference (backend endpoints)
- `POST /api/save_score` — save a game result
- `GET /api/progress/<user_id>` — get a user's game history
- `POST /api/set_stage` — set a patient's dementia stage
- `GET /api/get_stage/<user_id>` — get a patient's stage
- `POST /api/update_location` — send current GPS location
- `GET /api/latest_location/<user_id>` — get the last known location

## Team Workflow
- Before starting work: `git pull`
- After finishing something: `git add .` → `git commit -m "message"` → `git push`
- Message the group before editing a file someone else likely owns
