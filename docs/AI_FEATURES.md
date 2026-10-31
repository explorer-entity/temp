# AI PERSONALIZATION — Implementation & Roadmap

## Why AI here?
Dementia is heterogeneous: two patients at the same clinical stage can differ wildly in
fluid intelligence, education, language and mood. A static game difficulty either
frustrates (too hard → abandonment) or bores (too easy → no therapeutic benefit).
The optimal band is Vygotsky's *Zone of Proximal Development* — continuously tracked by AI.

## What is IMPLEMENTED today (`/api/ai/recommendations/<user_id>`)
A transparent, deterministic engine (no black box — important for clinicians):

1. **Stage-normalised scoring** — raw scores are divided by a baseline derived from the
   patient's dementia stage (`Early 0.85, Moderate 0.65, Severe 0.45`), so a 60 for a
   severe-stage patient counts as strong performance while the same 60 for an early-stage
   patient does not.
2. **Exponential Moving Average (EMA, α = 0.4)** over the last ≤10 sessions per game —
   recent performance weighs more, giving fast adaptation and noise damping.
3. **Difficulty policy**: EMA > 0.8 → `Hard`; < 0.4 → `Easy`; else `Medium`.
4. **Spaced repetition priority**: `priority = 0.6·EMA + 0.4·min(idle_days,7)/7` — games
   not touched for days are nudged back into the daily rotation.
5. **Client-side effects**:
   - *Word–Picture Match*: recommended difficulty sets round count (3/6/8), pulls from a
     larger item pool, and Fisher-Yates-shuffles options so correct-answer position and
     item order are never memorised.
   - *Story Detective*: game starts directly at the AI-recommended rung of its ladder
     instead of always Easy.
   - Both fall back gracefully to default behaviour if the server is unreachable (offline-first).
6. Every score save records the difficulty actually played → closed feedback loop.

## Roadmap (documented, not yet built)
| Phase | Feature | Approach |
|---|---|---|
| 1 | Per-item difficulty calibration | IRT-style: track p(correct) per word/story, select items targeting ~70-85% success |
| 2 | Session-length & time-of-day modelling | Learn each patient's best play window; schedule reminders accordingly |
| 3 | LLM content generation | GPT/Bhashini-class models generate stories & distractors in the patient's language + local NER context (Guwahati markets, Brahmaputra etc.), filtered through a safety layer |
| 4 | Voice biomarkers | Onset of dysfluency/pauses in Ask Smriti interactions → early decline signal (research-grade, needs consent) |
| 5 | Longitudinal decline detection | Weekly EMA trend per cognitive domain → caregiver "consult your neurologist" nudges; feed scores into MMSE/MoCA correlation study |
| 6 | Reinforcement-learning policy | Contextual bandit choosing difficulty transitions to maximise engagement × accuracy |

## Guardrails
- AI never *diagnoses*; it only personalises exercise difficulty and flags trends to humans.
- Recommendations include a human-readable `rationale` string for clinician trust.
- All training data must be de-identified and DPDP-Act compliant (see docs/ROADMAP.md).
