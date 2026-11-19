# PROJECT_STATE.md

## Done
- Hardened `main.py` Gemini call (`responseMimeType: "application/json"` + retry on transient 503/errors) and expanded `auto_pilot.py` topic history window to `past_topics[-80:]` while preserving existing Stoic prompts, philosopher rotation, queries, and 2x/day prime-time schedule.

## Current State
- `youtube-shorts-stoic-bot` updated and verified (`py_compile` + Gemini smoke test).

## Next Step
- Monitor ongoing Stoic Shorts & Long-Form cross-linked performance.
