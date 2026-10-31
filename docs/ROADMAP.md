# ROADMAP — Other Needed Changes (documented, pending)

## A. Security & accounts (highest priority before real deployment)
1. **Authentication** — currently any client can POST scores/locations for any `user_id`.
   Add PIN-based login (patients) + password/OTP (caregivers), JWT/session tokens, and
   server-side authorisation checks (caregiver may read only linked patients).
2. **Input validation & rate limiting** on all endpoints (Flask-WTF / marshmallow, flask-limiter).
3. **HTTPS + hashed passwords** (bcrypt); move SQLite → PostgreSQL for concurrency.

## B. Privacy & ethics (DPDP Act 2023)
4. Explicit informed-consent flow with plain-language (vernacular) explanations of what
   location data is collected, why, and retention period.
5. Data-retention policy: prune `Locations` older than N days unless flagged for a missing-person case.
6. "Caregiver viewed my location" audit log visible to the patient/family — anti-surveillance transparency.
7. Consent revocation must stop ingestion server-side, not just client-side.

## C. Native mobile apps (the two-app vision)
8. Wrap both PWAs in Capacitor/React Native → Play Store / App Store builds.
9. Patient app: Android foreground service + `GeofencingClient` (iOS: `CLCircularRegion`)
   for battery-efficient background monitoring; offline-first game cache; wearable (smartwatch) SOS.
10. Caregiver app: push notifications (FCM) for breach/SOS alerts instead of 4 s polling;
    multi-caregiver roles (family vs. paid aide) with granular permissions.

## D. Backend robustness
11. Persist the outside-ping streak in DB (currently in-memory, lost on restart).
12. Background job (APScheduler/Celery) to check reminders server-side and dispatch pushes
    even when the patient tab is closed.
13. Unit tests for Haversine/zone logic and the AI engine; CI via GitHub Actions.
14. Proper error handling & user-facing retry toasts instead of console.error.

## E. Clinical & content
15. Validated instrument alignment (MoCA domains) + clinician portal with exportable PDF trend reports.
16. More games per domain: spatial navigation, prosody/emotion recognition, music-evoked memory.
17. Vernacular voice packs beyond en-IN (Assamese/Bengali TTS via Bhashini APIs).
18. Community-mode leaderboard between care homes (opt-in, anonymised).

## F. Connectivity realities (NER)
19. Full offline mode: IndexedDB queue of scores/pings synced opportunistically.
20. SMS fallback channel for SOS when there is no data connection.
