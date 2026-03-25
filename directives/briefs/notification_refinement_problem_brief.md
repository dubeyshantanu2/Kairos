# Problem Brief — Notification Refinement

**Date:** 2026-03-25
**Status:** draft

## Problem Statement (Original)
to avoid over spamming of live updates we have added a condition where if the conditions changes one to another then only if will show me the update in the channel, i want to add a condition where initailly the the system is strted it should give the update then it should follow the no spamming policy.

## Problem Statement (Simplified)
Ensure the first successful scoring cycle of a session always triggers a Discord alert, regardless of status. Subsequent cycles follow the existing change-detection filter.

## What We Know
- The current implementation in `src/kairos/scheduler.py` filters environment alerts.
- Alerts are only sent if `score.state_changed` is true AND the status is "GO" or leaving "GO".
- On startup/reset, `state.previous_status` is `None`, so `state_changed` is true, but the filtering condition usually blocks it unless it's a "GO" signal.

## What We Don't Know (Assumptions to Validate)
- Does "initially the system is started" include every time a session resets (e.g., Session 1 vs Session 2)?
    - *Assumption:* Yes. Any time `previous_status` is `None` (start of scoring sequence), we should send an update.

## Edge Cases Identified
- **Session configuration changes** (`state.startup_done = False`, `reset_buffers()` called). This should trigger a new "first" update.
- **Failures at startup**. The update should only happen once a valid score is produced.

## recommended Next Step
→ Software Architect Agent (create ADR for implementation details)
