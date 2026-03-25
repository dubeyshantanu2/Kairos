# ADR-008: Initial Session Alert

**Date:** 2026-03-25
**Task ID:** NOTIF-001

## Problem Statement
The current Discord notification strategy (ADR-007) is highly effective at reducing noise by only alerting on "Signal Start" (GO) or "Signal End" (leaving GO). However, this results in a lack of immediate feedback when the system starts or resets if the initial status is CAUTION or AVOID. The user needs confirmation that the system is scoring correctly at the beginning of each session.

## Decision and Rationale
We will modify the session gate logic in `scheduler.py` to call `state.reset_buffers()` every time a new session starts (e.g., at 9:15 AM and 1:00 PM).

**Rationale:**
- **Proof of Life:** Clearing `previous_status` ensures the cumulative scoring cycle identifies the first cycle of a new session window as `is_first_cycle`, triggering a mandatory Discord update regardless of market status.
- **Data Integrity:** Resetting buffers at the session boundary (e.g., after lunch) prevents stale data from the morning session from contaminating momentum and VWAP calculations.
- **Observability:** Maintains a strict "one message per session" confirmation while preserving the noise-reduction policy for all subsequent intraday updates.

## Implementation Details
1.  In `src/kairos/scheduler.py`, inside the session boundary check of `run_cycle()`:
    ```python
    if not state.in_session:
        state.in_session = True
        state.reset_buffers()  # Ensure fresh start + triggers alert
        await notifier.post_session_boundary(...)
    ```
2.  The alert filtering logic uses `is_first_cycle = (state.previous_status is None)` to permit the initial signal.

## API Contracts / File Assignments
- **`src/kairos/scheduler.py`**: Modify the alert evaluation block in `run_cycle`.

## Definition of Done
- The first successful cycle of a session sends a Discord alert even if status is AVOID.
- Subsequent "AVOID -> AVOID" or "AVOID -> CAUTION" transitions DO NOT send alerts.
- Transitions to "GO" or from "GO" continue to send alerts.
- Existing tests pass.
