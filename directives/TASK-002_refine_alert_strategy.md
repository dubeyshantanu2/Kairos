# TASK-002 Refine Alert Strategy
**Date:** 2026-03-24
**Status:** ready

## Goal
Minimize Discord noise by restricting notifications to critical lifecycle events (Start/End) and process issues (Errors/Warnings).

## Inputs
- Current `notifier.py` and `scheduler.py` implementations.
- User preference for "Start, End, and Issues" only.

## Tools / Scripts to Use
- `src/kairos/notifier.py`
- `src/kairos/scheduler.py`

## Expected Output
- Refined alerting logic that suppresses non-critical updates.
- Updated documentation (ADR-007).

## Acceptance Criteria
- Discord notifications only trigger for:
    - Engine Start / Session Start / Warmup Complete ("Start").
    - Session End / Engine Stop ("End").
    - Functional/Connectivity Issues (Dhan API errors, Supabase errors, Stale signals) ("Issues").
- **Environment Status alerts** in `#environment` are suppressed EXCEPT when transitioning to a "GO" state (Start of opportunity) or if specifically requested.
- Local logs continue to record all intermediate states for diagnostic purposes.

## Edge Cases
- **Silent failure:** Ensure that "Stale Signal Detection" (the failsafe for silent process hangs) remains highly visible as an "Issue".
