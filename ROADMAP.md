# ROADMAP — status

Legend: ✅ done in this repo · 🟡 partly done · ⬜ open

## A. Security & accounts
1. ✅ Authentication — patient PIN + caregiver password, session tokens, per-patient authorisation (`MANOVA_AUTH=off` keeps the old demo mode)
2. 🟡 Input validation ✅ · rate limiting ✅ on login/link-code only (add flask-limiter for the rest)
3. 🟡 Hashed secrets ✅ (werkzeug) · HTTPS ⬜ (terminate TLS in a reverse proxy) · PostgreSQL ⬜

## B. Privacy & ethics (DPDP Act 2023)
4. 🟡 Consent: explicit toggle + server-side enforcement ✅ · vernacular plain-language explanation ⬜ · retention period shown in-app ⬜
5. ✅ Retention: pings auto-pruned after `LOCATION_RETENTION_DAYS` (kept while an alert is active)
6. ✅ "Who viewed my data" audit log, visible to the patient
7. ✅ Consent revocation stops ingestion server-side · ✅ erasure (`/api/erase_my_data`) · ✅ patient can remove a caregiver

## C. Native mobile apps
8-10. ⬜ See `docs/NATIVE_APPS.md`. Live in-browser push via SSE ✅ (dashboard open); FCM/background geofencing ⬜

## D. Backend robustness
11. ⬜ Persist the outside-ping streak in DB (still in memory)
12. ⬜ Server-side reminder scheduler
13. 🟡 Tests: scripted API suite exists (see paper Appendix A); CI ⬜
14. 🟡 Error handling: 400s instead of crashes ✅; retry toasts ⬜

## E. Clinical & content
15. 🟡 MoCA entry, weekly trends, correlation, decline nudge, printable report ✅ · validated clinical study ⬜
16-18. ⬜ More games, vernacular voice packs, community mode

## F. Connectivity realities (NER)
19. 🟡 Offline outbox for scores, pings and SOS ✅ · full offline game cache beyond the PWA shell ⬜
20. 🟡 SOS-by-SMS fallback (opens the SMS app, patient presses send) ✅ · server-side SMS gateway ⬜
