# Native apps: background geofencing and true push (NOT built yet)

The web apps work while the app/tab is open. Two things a browser cannot do reliably:

1. **Background location** when the phone is locked: needs a native app.
2. **Push when the dashboard is closed**: needs FCM/APNs credentials.

Plan (untested, needs Android Studio / Xcode and your own Firebase project):
- Wrap `static/` with Capacitor (`npm i @capacitor/core @capacitor/cli`, `npx cap add android`).
- Patient app: a background-geolocation plugin (e.g. `@capacitor-community/background-geolocation`) calling
  the existing `POST /api/update_location`; Android foreground service + `GeofencingClient` to cut battery use.
- Caregiver app: `@capacitor/push-notifications` + FCM; add a `PushTokens` table and send from `_publish_alert()` in `app.py`
  (the single place every alert passes through).
- Keep the consent gate: the server already refuses pings until `/api/consent` is on.
