# PROJECT_STATE.md

## Done
- Assigned dedicated British voice (`en-GB-RyanNeural`, `rate=+2%`, `pitch=-2Hz`) and antique-bronze instant `t=0.0` hook caption identity in `main.py`.
- Upgraded script prompt to 5–6 scenes / 75–95 words (28–36s target) with `<62`-word retry guard, closing Stoic comment question, and `_clean_stoic_title`.
- Added topic + title token-overlap deduplication (`_is_duplicate_stoic_item`, `_ensure_unique_title`) in `auto_pilot.py` alongside philosopher rotation.
- Focused Shorts to 1x/day US prime-time (`22:00 UTC`, 18h spacing in `uploader.py` & `daily_stoic_shorts.yml`) and reduced `weekly_long_stoic.yml` to 1x/week (Sunday `16:00 UTC`); verified with `py_compile` + unit checks.

## Current State
- `youtube-shorts-stoic-bot` updated, verified, and pushed to `origin/main`.

## Next Step
- Monitor 1x/day Stoic Shorts (`22:00 UTC`) and Sunday Long-Form cross-linked performance over the next 5–7 days.
