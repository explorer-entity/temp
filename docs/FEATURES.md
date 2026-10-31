# FEATURES — What Every Part of the System Does

## 1. Patient App (`static/home.html`)
| Screen | What it does |
|---|---|
| Home | Four large touch targets (Games, Progress, Family, SOS) sized for tremor/vision impairment; one-tap purple "Ask Smriti" voice button |
| Games | Launches Word–Picture Match and Story Detective, passing the chosen language |
| Progress | Pulls `/api/progress/<id>` — total games, best score, streak; motivates the patient and feeds caregivers |
| Family | Saved contacts with one-tap calling (tel: links) |
| SOS / Lost My Way | POSTs a `Lost My Way` alert to the backend (appears instantly on the caregiver dashboard) and opens the live map + shares location |
| Profile | Name, stage, language selection; explicit **location consent** button (privacy-first) |
| Location | Leaflet map centred on device GPS; every fix is POSTed to `/api/update_location`, which drives geofence checking |
| Reminders | Polls `/api/reminders/<id>` every 30 s; when due, speaks the reminder (TTS) and fires a push notification via the service worker |
| Localization | Full UI strings in English, Hindi, Bengali and Assamese — critical for the North-Eastern Region |

## 2. Games
- **Word–Picture Match**: naming/recognition drill (semantic memory). Tap or speak the answer. Now AI-personalised (see docs/AI_FEATURES.md).
- **Story Detective**: short story → comprehension questions under a countdown; difficulty ladder rises/falls with performance (attention, working memory, reasoning). Now starts at the AI-recommended level.

## 3. Ask Smriti voice assistant (`ask-smriti-demo.html`)
Web Speech API STT + TTS Q&A ("What is today's date?", "Where is my daughter?"). Reduces anxiety through familiar conversational access to routine information.

## 4. Caregiver App (`static/caregiver-dashboard.html`)
- Register as caregiver, link patients by ID, switch between multiple patients.
- Live Leaflet map: latest position marker, **multiple named geofence circles**, dashed **movement-trail polyline** (last 50 pings).
- Safe-zone manager: name + radius inputs, save-at-last-location, list & delete zones.
- Alert feed (geofence breaches + SOS), daily reminder management, cognitive progress stats, quick actions.
- Auto-refresh every 4 s.

## 5. Backend (`app.py`)
Flask REST API over SQLite: users/links, game scores & progress, location ingestion with multi-zone geofence evaluation (Haversine, 2-ping debounce), alerts, reminders, and the AI recommendation engine.

## 6. PWA layer (`manifest.json`, `sw.js`)
Installable on Android without an app store; caches the shell so games still open on the patchy rural networks typical of the NER.
