# ADR-008: Initial Session Alert

**Date:** 2026-03-25
**Task ID:** NOTIF-001

## Problem Statement
The current Discord notification strategy (ADR-007) is highly effective at reducing noise by only alerting on "Signal Start" (GO) or "Signal End" (leaving GO). However, this results in a lack of immediate feedback when the system starts or resets if the initial status is CAUTION or AVOID. The user needs confirmation that the system is scoring correctly at the beginning of each session.

## Decision and Rationale
We will modify the alert filtering logic in `scheduler.py` to allow the first successful scoring cycle of any session/reset to trigger an alert, regardless of the status.

**Rationale:**
- Provides "proof of life" for the scoring engine early in the session.
- Only adds 1 additional message per session (morning, afternoon, or on config reset).
- Maintains the "no-spam" policy for all subsequent cycles.

## Implementation Details
1.  In `src/kairos/scheduler.py`, inside `run_cycle()`, detect if this is the first successful scoring cycle.
2.  A new Boolean flag `is_first_cycle = (state.previous_status is None)` can be used before `state.previous_status` is updated.
3.  Update the `if` condition for `notifier.post_environment_alert(score)` to include `is_first_cycle`.

## API Contracts / File Assignments
- **`src/kairos/scheduler.py`**: Modify the alert evaluation block in `run_cycle`.

## Definition of Done
- The first successful cycle of a session sends a Discord alert even if status is AVOID.
- Subsequent "AVOID -> AVOID" or "AVOID -> CAUTION" transitions DO NOT send alerts.
- Transitions to "GO" or from "GO" continue to send alerts.
- Existing tests pass.
