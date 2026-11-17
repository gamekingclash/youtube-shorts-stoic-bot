# PROJECT_STATE.md

## Done
- Fixed metadata JSON filename mismatch in `auto_pilot.py` (now checks both `.json` and `_metadata.json` so Gemini titles/descriptions are no longer discarded).
- Replaced copy-pasted Finance fallback script in `main.py` with genuine Stoic philosophy fallback and added clean title normalization (`<=55` chars + `#shorts`).
- Added philosopher rotation in `auto_pilot.py` to avoid back-to-back Seneca/Marcus/Epictetus repeats.
- Added `get_next_stoic_publish_time` in `uploader.py` (`22:00` & `01:00 UTC` US prime slots with collision avoidance).

## Current State
- Stoic Wisdom bot updated with working metadata resolution, philosopher rotation, Stoic fallback, and US prime-time scheduling.

## Next Step
- Push changes to `origin/main` and monitor upcoming Stoic Shorts variety and performance.
