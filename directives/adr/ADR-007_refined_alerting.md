# ADR-007: Refined Alert Strategy (Start/End/Issue Only)
**Date:** 2026-03-24
**Status:** Proposed

## Problem Statement
The user reported excessive Discord noise and requested that alerts be restricted to "Start, End, and Issues". This requires a more aggressive suppression policy than just silencing the heartbeat.

## Decision
1.  **Strict Lifecycle Alerts:** Only the following "Start/End" events will trigger Discord notifications:
    - `post_startup` (Engine Start)
    - `post_session_boundary(entering=True)` (Session Start)
    - `post_warmup_complete` (Warmup Complete - considered part of Start)
    - `post_session_boundary(entering=False)` (Session End)
    - `post_stopped` (Engine Stop)
2.  **Issue-Only Monitoring:** All current issue-based alerts remain active:
    - `post_api_warning` / `post_api_recovered`
    - `post_critical_alert`
    - `post_stale_signal_warning`
3.  **Environment Status Suppression:** 
    - `post_environment_alert` (GO/CAUTION/AVOID) will now be suppressed **UNLESS** the status changes to **"GO"** (Transition from non-GO to GO).
    - Status changes back to CAUTION/AVOID will also be suppressed unless they are part of a recovery from an "Issue".
    - *Rationale:* Transitions to "GO" are "Start of Opportunity" events, whereas intermediate fluctuations are considered noise.
4.  **Local Persistence:** All scoring results and cycles will continue to be written to the Supabase `environment_log` and local `logs/kairos.log`.

## Rationale
- **High Signal-to-Noise Ratio:** Responds to the user's specific request for minimal interruptions.
- **Functional Integrity:** Keeps the system's "Signal" (GO signal) visible while silencing the "Market Commentary" (frequent CAUTION/AVOID updates).
- **Security:** Error alerts are preserved to ensure the user is notified immediately if the system fails.

## Component Changes
- `src/kairos/scheduler.py`: Add logic to conditionally call `notifier.post_environment_alert`.
- `src/kairos/notifier.py`: Ensure that local logging remains robust for suppressed alerts.

## Definition of Done
- [ ] No Discord alerts for CAUTION or AVOID status changes.
- [ ] Verified Discord alerts for: Startup, Session Start, Warmup Complete, Session End, and GO signals.
- [ ] Verified Discord alerts for simulated API failures.
- [ ] All tests in `tests/test_scheduler.py` updated and passing.
