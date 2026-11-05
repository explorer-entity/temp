# Building the Manova Android APK

The repo now contains a **Capacitor** native shell (`android/` project + `capacitor.config.json`).
It wraps the same web app (patient app, games, Ask Smriti, caregiver dashboard) in an installable APK.

## Prerequisites
- JDK 17 ✔ (already available here)
- Android SDK (platform-tools, build-tools;34, platform;android-34) — NOT installed in this sandbox
- `ANDROID_HOME` env var pointing at the SDK

## Steps (on any machine with the SDK)
```bash
npm install                 # capacitor cli/core/android already in package.json
npx cap sync android        # copies capwww/ -> android/app/src/main/assets/public
cd android && ./gradlew assembleDebug
# APK appears at: android/app/build/outputs/apk/debug/app-debug.apk
```

## How it talks to the backend
- The WebView loads bundled assets from `capwww/` (offline UI).
- All `/api/*` calls are routed to `window.API_BASE`:
  - Native build → `http://10.0.2.2:5000` (host-loopback alias on Android emulators).
  - Physical device → edit `capacitor.config.json` `server.url` and `API_BASE` in `capwww/*.html`
    to your LAN IP, e.g. `http://192.168.1.50:5000`, then re-run `npx cap sync android`.
- Web/PWA mode is unaffected (`static/index.html` pins `API_BASE=""`).

## Notes
- `server.cleartext: true` allows HTTP during development; use HTTPS in production.
- Production should add OS-level geofences via `@capacitor/geolocation` + background task plugin
  (see docs/ROADMAP.md) instead of JS polling.
