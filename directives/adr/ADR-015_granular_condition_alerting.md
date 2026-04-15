# ADR-015: Granular Condition and Status Alerting
**Date:** 2026-04-15
**Status:** Approved

## Problem Statement
The user requested high-frequency visibility into market status, specifically wanting to be notified of *any* change in the underlying condition values (e.g., IV fluctuations, momentum shifts) as well as all environment status transitions (GO, CAUTION, AVOID). This directly reverses the noise-reduction strategy established in ADR-007, which limited alerts to "Start, End, and Issues."

## Decision
1.  **Abolish Environment Alert Suppression:** We will remove the filters that suppressed CAUTION and AVOID alerts. Every status transition (GO ↔ CAUTION ↔ AVOID) will now trigger a Discord notification.
2.  **Granular Condition Tracking:** The system will now track the `detail` string and `status` of each of the 7 scoring conditions across cycles.
3.  **Alert on Value Changes:** Any change in a condition's `status` or its human-readable `detail` text (which contains live calculated values) will trigger a `post_environment_alert`.
4.  **Warmup Completion Alert:** The warmup completion notification remains a mandatory trigger for an environment alert.

## Rationale
- **Market Awareness:** Fulfils the user's requirement to stay "aware of what's the current status going on in the market" on a minute-by-minute basis.
- **Transparency:** Provides the trader with the full context of why a status changed or is holding, rather than just the final result.
- **User Preference:** Directly responds to explicit user feedback requesting higher signal density.

## Component Changes
- `src/kairos/scheduler.py`: 
    - Update `SessionState` to track `previous_conditions`.
    - Modify `run_cycle` to detect changes in condition status/details.
    - Update the logic in section 11 (Alerting) to trigger alerts on any status change, condition change, or warmup completion.

## Definition of Done
- [ ] Discord alerts triggered for GO, CAUTION, and AVOID transitions.
- [ ] Discord alerts triggered every minute if any underlying condition value (e.g., VWAP distance, IV change) fluctuates.
- [ ] Warmup completion triggers a full environment alert.
- [ ] Tests in `tests/test_scheduler.py` verified and adjusted for new alerting behavior.
