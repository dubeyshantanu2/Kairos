# ADR-006: Issue-Only Health Reporting
**Date:** 2026-03-24
**Status:** Proposed

## Problem Statement
The periodic heartbeat message (currently every 5 minutes) in `#system-check` creates excessive noise, making it difficult for the user to distinguish between normal operations and actual system issues.

## Decision
1.  **Silence Routine Heartbeats:** Deactivate the `notifier.post_heartbeat()` call within the periodic `run_heartbeat` job in `scheduler.py`.
2.  **Preserve Background Monitoring:** The `run_heartbeat` job itself will continue to run every 5 minutes to perform critical health checks, specifically **Stale Signal Detection** (checking if the scoring cycle has hung).
3.  **Retain Lifecycle Alerts:** Notifications for major engine events will remain active:
    - Engine Startup (`post_startup`)
    - Session Start/End (`post_session_boundary`)
    - Warmup Completion (`post_warmup_complete`)
    - Manual Stop (`post_stopped`)
4.  **Issue-Driven Alerts:** All existing error and warning alerts remain unchanged (Dhan API failures, Supabase connectivity, process stalls).
5.  **Diagnostic Logging:** All data previously sent in the heartbeat (cycle count, last fetch time, warmup status) will continue to be logged to `logs/kairos.log` at the `INFO` level.

## Rationale
- **User Experience:** Directly satisfies the user's request for a cleaner Discord environment.
- **Critical Oversight:** By keeping "Stale Signal Detection" active, we ensure that a silent crash or hang *still* triggers a Discord alert (`post_stale_signal_warning`), providing the safety of a heartbeat without the noise.
- **Maintainability:** Minimal code changes required; keeps the door open for restoring heartbeats if troubleshooting requires it.

## Component Changes
- `src/kairos/scheduler.py`: Conditionalize or remove the `notifier.post_heartbeat` call in `run_heartbeat()`.
- `logs/kairos.log`: Verify heartbeat data is still logged locally.

## Definition of Done
- [ ] No "System alive" heartbeat messages appear in Discord during normal operation.
- [ ] Engine Startup and Warmup Completion messages still post successfully.
- [ ] Simulation of a hung engine (no `run_cycle` updates) triggers a "SIGNAL MAY BE STALE" alert.
- [ ] `logs/kairos.log` contains periodic state updates for diagnostic use.
