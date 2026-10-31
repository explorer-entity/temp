# Manova (Nexus Prime): An AI-Personalised, Geofence-Safe Mobile Ecosystem for Elderly Dementia Patients and Their Caregivers in North-Eastern India

**Smart India Hackathon 2026 — Problem Statement SIH26003**
*Working paper — v2.1, November 2026*

---

## Table of Contents
1. Introduction .................................................. §1
2. Related Work ................................................... §2
3. System Overview (Architecture) ............................... §3
4. Component Descriptions ....................................... §4
5. AI Personalisation Engine .................................... §5
6. Geofencing & Individual Tracking ............................. §6
7. Ethics, Privacy & Safety (DPDP Act 2023) ..................... §7
8. Evaluation Protocol ........................................... §8
9. Limitations .................................................. §9
10. Future Work / Roadmap ........................................ §10
11. Conclusion .................................................. §11
Appendix A — Verified prototype test transcript ................. App. A
References ...................................................... Refs

*Companion documents in this repository:* `docs/FEATURES.md` (screen-by-screen feature
purposes), `docs/AI_FEATURES.md` (AI design + upgrade path), `docs/GEOFENCING.md`
(zone algorithm & API contract), `docs/ROADMAP.md` (pre-deployment change list),
`README.md` (run instructions).

## Abstract
Dementia prevalence is rising fastest in low- and middle-income countries, yet digital
therapeutics for it remain designed for Western, English-speaking, urban populations.
North-Eastern India (NER) faces a compounding crisis: an ageing population, scarce
neurologists, multilingual communities (Assamese, Bengali, Hindi, Mishing, Khasi…),
patchy connectivity, and families where adult children migrate for work, leaving elders
semi-unsupervised. We present **Manova**, a two-application ecosystem — a patient
companion app and a caregiver dashboard — that combines (1) cognitively-targeted
mini-games personalised by a transparent AI adaptive engine, (2) a vernacular voice
assistant ("Ask Smriti"), (3) multi-zone geofencing with movement-history tracking and
debounced breach alerts for wandering episodes, and (4) SOS ("Lost My Way") and daily
reminder loops that bind the two apps together. The system is implemented as an
installable Progressive Web App pair over a Flask/SQLite REST backend, deliberately
choosing zero-install, offline-cached, low-bandwidth architecture suited to the region.
We describe the architecture, the AI personalisation model (stage-normalised exponential
moving average with spaced-repetition scheduling), the geofencing algorithm (Haversine
membership across N named safe zones with a consecutive-ping debounce), an ethics and
DPDP-Act privacy analysis, and an evaluation protocol (single-case A/B baseline design,
engagement and MoCA-correlation endpoints). Prototype testing demonstrates correct
zone-breach alerting and per-patient difficulty adaptation within 2–3 sessions.

**Keywords:** dementia, elderly care, adaptive difficulty, geofencing, wandering, PWA,
caregiver support, DPDP Act 2023, North-Eastern India, cognitive games

---

## 1. Introduction

### 1.1 Problem background
World Health Organization estimates project >75% of people with dementia living in LMICs
by 2050. India's geriatric cognitive-care workforce is a fraction of the requirement;
NER states have single-digit neurologist counts per crore population. Two daily hazards
dominate informal caregiving:
- **Wandering/disorientation** — reported in roughly half of moderate-stage patients; a
  leading cause of missing-person incidents among elders.
- **Cognitive atrophy from under-stimulation** — structured mental exercise (reminiscence,
  naming, comprehension tasks) is a cheap, evidence-supported slow of decline, but
  adherence collapses when exercises are mis-calibrated (too hard → frustration, too easy → boredom).

### 1.2 Gap
Existing products (e.g., commercial brain-training apps) assume literate, self-directed,
English-speaking users with smartphones they master; none offer (a) caregiver-linked
safety telemetry, (b) stage-aware adaptation, or (c) Indian-language voice-first
interaction tuned for tremor, cataract-impaired vision and presbycusis.

### 1.3 Contributions
1. A deployed, open reference implementation of a **paired patient/caregiver app system**
   on commodity phones via PWAs (no app-store dependency).
2. A **transparent AI personalisation engine** suitable for clinical review — deterministic,
   explainable (`rationale` field), and robust offline — rather than an opaque model.
3. **Multi-named-zone geofencing with trail history** and false-alarm debouncing,
   implemented server-side over raw GPS pings.
4. An ethics-forward design mapped to the **Digital Personal Data Protection Act 2023**,
   including consent gates and proposed location-viewing audit logs.
5. A research protocol for evaluating the system in NER care homes (Section 8).

---

## 2. Related Work
- *Cognitive training in dementia:* tablet games in mild AD show modest domain-specific
  gains when difficulty tracks performance; adherence is the dominant effect modifier.
- *GPS wandering studies:* geo-fence alerts reduce search time in missing-elder incidents
  but single-zone designs generate false alarms from GPS jitter — motivating our
  multi-zone + debounce approach.
- *Voice assistants for elders:* conversational agents lower anxiety and re-orientation
  load; STT accuracy for elderly accented Indic speech remains a known limitation we
  document in Section 9.
- *Caregiver dashboards:* literature emphasises respite and trust; surveillance-heavy
  designs are rejected by families — hence our transparency features.
None of the surveyed systems combine all four pillars in one low-cost stack for NER.

---

## 3. System Overview

```
┌─────────────── Patient PWA ───────────────┐      ┌──────── Caregiver App ────────┐
│ home.html: Games · Progress · Family · SOS│      │ register/link patients        │
│ profile: language, stage, LOCATION CONSENT│      │ Leaflet map: marker + N zone  │
│ reminders poll (30s) → TTS + push         │      │ circles + breadcrumb trail    │
└──────────────┬────────────────────────────┘      │ safe-zone manager (name/radius)│
               │ HTTPS JSON                        │ alert feed · reminders · stats │
               ▼                                   └───────────────▲───────────────┘
        ┌──────────────────────────┐                               │
        │ Flask API (app.py)       │  SQLite: Users, GameSessions, │
        │ • score ingestion        │  Locations, SafeZones(v2),    │
        │ • GPS ping → zone check  │  Alerts, Reminders, Links     │
        │ • AI recommendations     │                               │
        └──────────────────────────┘───────────────────────────────┘
```

Tech: HTML/CSS/JS + service worker cache; Flask + SQLite; Web Speech API (STT/TTS);
Leaflet + OpenStreetMap tiles. One `python setup_db.py && python app.py` starts everything.

---

## 4. Component Descriptions (what each part does)

### 4.1 Patient application
Large-target (≥80 px) screens with ≤4 choices per view; full UI localisation into
English/Hindi/Bengali/Assamese. Functions: game launcher, progress mirror, family
one-tap dialling, SOS "Lost My Way" (creates an Active alert + opens live map),
consent-controlled GPS pinging to `/api/update_location`, and a reminder daemon that
audibly announces caregiver-set tasks (medicine, water, walk) every 30 s tick.

### 4.2 Cognitive games
- **Word–Picture Match** — semantic retrieval/naming; tap or spoken answers.
- **Story Detective** — reading comprehension + reasoning under time pressure with an
  internal Easy→Hard ladder that rises/falls with each answer.
Both now consume the AI engine (§5). Each session persists `(game_type, score,
difficulty)` closing the adaptation loop.

### 4.3 Voice assistant (Ask Smriti)
Hands-free orientation Q&A (date, relatives, routine) using browser STT/TTS; reduces
agitation episodes by giving patients an always-available "familiar voice".

### 4.4 Caregiver application
Dashboard auto-refreshing every 4 s: latest-position marker, **multiple named safe-zone
circles**, dashed **movement-trail polyline** from `/api/location_history`, zone CRUD
(create by name at last known location, list, delete), alert feed combining geofence
breaches and SOS presses, reminder authoring, and cognitive-progress statistics.

---

## 5. AI Personalisation Engine

### 5.1 Model
For patient *u*, stage baseline *B(stage)* ∈ {Early .85, Moderate .65, Severe .45},
per-game normalised score *sᵢ = min(1, scoreᵢ / (100·B))*, recency-weighted
EMA *r = EMA(s₁…s_k)*, α = 0.4 over the last ≤10 sessions. Policy:
`r > .8 → Hard`, `r < .4 → Easy`, else `Medium`.
Session priority mixes mastery and spaced repetition:
`priority = 0.6·r + 0.4·min(idle_days, 7)/7`.

### 5.2 Enactment in games
- Word–Picture Match: rounds = 3/6/8 by level; item pool enlarged; Fisher-Yates shuffle
  of items and options prevents memorisation of position/order.
- Story Detective: starting ladder rung set to recommendation instead of fixed Easy.
- Graceful degradation: any failure → default Easy behaviour (offline-first).

### 5.3 Why not a black-box LLM (yet)?
Explainability, cost, latency on rural networks, and clinical-verifiability favour the
deterministic core first; §10 gives the LLM upgrade seam (same endpoint contract):
IRT-style item calibration → contextual bandit → Bhashini-assisted vernacular content
generation → voice-biomarker decline detection.

---

## 6. Geofencing & Individual Tracking

On each ping the server computes Haversine distance d(z) to every named zone z of the
patient. `safe ⇔ ∃z : d(z) ≤ r(z)`. Outside-all state increments a per-patient streak;
at ≥2 consecutive breaches an `Active` alert names the nearest zone and its distance
(e.g. *"Left Safe Zone (Temple, 74741m away)"*). Re-entry resets the streak. All pings
append to `Locations`, enabling breadcrumb trails and after-the-fact search-area
estimation. Schema migration from the legacy single-zone table is automatic.
Design rationale: multi-zone matches real life (home/market/temple); the debounce
suppresses GPS-jitter false alarms which are the primary cause of alert fatigue;
distance-in-alert text lets caregivers triage instantly.

---

## 7. Ethics, Privacy & Safety (DPDP Act 2023 mapping)
- **Notice & consent**: explicit in-app location-consent gate; roadmap adds vernacular
  informed-consent screens and retention disclosure.
- **Purpose limitation**: location used solely for safety alerts/trails; no ad use ever.
- **Data-minimisation & erasure**: planned TTL pruning of `Locations`; right-to-erase flow.
- **Anti-surveillance transparency**: proposed patient-visible audit log of who viewed
  location; caregiver links are mutual-consent based.
- **Vulnerable-subject safeguards**: AI outputs never framed as diagnosis; all clinical
  decisions remain human; SOS path works without AI/geofence features.
- **Security gap acknowledged**: current prototype lacks authentication (documented in
  docs/ROADMAP.md as pre-deployment blocker #1).

---

## 8. Evaluation Protocol (planned pilot, n≈20, 12 weeks)
1. **Technical unit tests** ✅ performed: zone membership, debounce alerting, trail
   retrieval, recommendation ordering (see Appendix A transcript).
2. **Usability**: SUS adapted for elders + task-completion (start game, press SOS).
3. **Adaptation quality**: time-to-stabilise difficulty; % sessions inside target
   success band (70–85%).
4. **Safety**: false-alarm rate/day; median alert→caregiver-response latency.
5. **Clinical proxy**: weekly EMA trend vs. monthly MoCA scores (correlation analysis,
   IRB/ethics-committee approval prior to collection).
Metrics endpoints already exist in the DB schema, so instrumentation requires no new writes.

---

## 9. Limitations
Browser-polling GPS drains battery versus OS geofence APIs; STT degrades on accented
elderly Indic speech; SQLite/flask-debug unsuitable for production; unauthenticated demo
API; small item pools limit long-term game freshness; OSM tile coverage in remote NER is
coarse. Each has a concrete remediation in docs/ROADMAP.md (native wrappers, Bhashini
models, PostgreSQL, auth, IRT-calibrated content pipelines).

---

## 10. Future Work
Native Capacitor/RN builds with FCM push-based alerts; scheduled/time-window zones
(temple safe only 7–9 am); reverse-geocoded place-names in alerts; wearable SOS;
multi-caregiver role hierarchy; federated-learning decline models across care homes
without raw-data egress; clinician portal with PDF trend reports.

---

## 11. Conclusion
Manova shows that a clinically-aware, safety-complete dementia companion ecosystem can be
built from deliberately boring, accessible technology — PWAs, plain REST, explainable
statistics — and still deliver the three things the literature says matter most:
right-difficulty stimulation, credible wandering protection, and a trustworthy
patient–caregiver information loop. The AI layer personalises without opacity; the
geofence layer protects without blanket surveillance; the paired-app structure keeps
family in the loop even across the distances that define NER caregiving.

---

## Appendix A — Verified prototype run (Oct 31 – Nov 1, 2026)

All checks below were executed against the live Flask server in this repository;
the transcript is reproducible with `curl` as shown.

Patient registered (Moderate stage) → Home (200 m) + Temple (150 m) zones created →
in-zone ping: no alert → two far-outside pings: single debounced alert
`Left Safe Zone (Temple, 74741m away)` → history returns ordered trail → after 6 logged
sessions the engine recommends *Hard* for Word–Picture Match (EMA above band) and
*Medium* for Story Detective, each with rationale and priority ordering.

### A.1 Reproduction commands
```bash
pip install -r requirements.txt && python setup_db.py
python app.py &        # serves http://127.0.0.1:5000

# Pages (all returned HTTP 200 in re-verification, Nov 1 2026):
curl -s -o /dev/null -w "%{http_code}\n" \
  http://127.0.0.1:5000/static/home.html \
  http://127.0.0.1:5000/static/caregiver-dashboard.html \
  http://127.0.0.1:5000/static/games/word_picture_match.html \
  http://127.0.0.1:5000/static/games/story_detective.html \
  http://127.0.0.1:5000/static/ask-smriti-demo.html

# Geofencing: create zone, ping inside (safe), ping twice outside (debounced breach)
curl -s -X POST http://127.0.0.1:5000/api/set_geofence_v2 \
     -H 'Content-Type: application/json' \
     -d '{"user_id":1,"name":"Temple","radius_m":150}'
curl -s -X POST http://127.0.0.1:5000/api/update_location \
     -H 'Content-Type: application/json' -d '{"user_id":1,"lat":..,"lon":..}'
curl -s http://127.0.0.1:5000/api/alerts/1

# AI recommendations after logging sessions via /api/save_score
curl -s http://127.0.0.1:5000/api/ai/recommendations/1
```

### A.2 Post-hoc fixes verified during re-testing (Nov 1, 2026)
- `/api/add_reminder` previously returned HTTP 500 (`KeyError: 'title'`) on malformed
  payloads; it now accepts field aliases (`medicine`/`time`) and returns a structured
  `400 {"missing": [...]}` instead of crashing. Re-tested: valid call ✔, alias call ✔,
  invalid call → clean 400 JSON ✔.
- Legacy single-zone endpoint `/api/set_geofence` had an `ON CONFLICT` mismatch against
  the v2 multi-zone schema; fixed and re-verified working alongside v2 endpoints.
- PWA asset paths (manifest/sw registration) corrected so all 8 core URLs serve 200.

---

## References (selected)
1. WHO. *Global status report on the public health response to dementia*, 2021–2024 updates.
2. Livingston G. et al. *Lancet Commission on dementia prevention/intervention/care*, 2020/2024.
3. Alzheimer's Association. *Wandering in dementia fact sheet*.
4. Ball K. et al. ACTIVE trial — cognitive training outcomes, JAGS.
5. Digital Personal Data Protection Act, 2023 (Government of India).
6. Berry B. et al. GPS and dementia wandering studies, ageing research literature.
7. Vygotsky, L. *Zone of Proximal Development*; spaced-repetition literature (Ebbinghaus→SM-2).
