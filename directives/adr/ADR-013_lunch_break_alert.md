# ADR-013: Lunch Break No-Trading Alert

**Date:** 2026-04-13
**Task ID:** NOTIF-002

## Problem Statement
When session 1 ends at 11:45 IST and session 2 begins at 13:00 IST, the engine
enters a silent idle state with no notification to the trader. During this 75-minute
gap the trader receives no feedback — they may assume the system has failed, or worse,
continue trading based on the last stale signal from the morning session.

## Decision and Rationale
We will add a dedicated **lunch break alert** that fires once when the engine enters
the gap between `session_1_end` and `session_2_start`. The alert is posted to **both**
the `#environment` and `#system-check` Discord channels.

**Rationale:**
- **Trader Safety:** Explicitly tells the trader not to trade during the dead zone.
  The last GO/CAUTION signal from session 1 becomes stale after 11:45 and must not
  be acted upon.
- **Observability:** Removes ambiguity about whether the engine is alive or crashed.
  The trader sees a clear "engine idle, will resume at 13:00" message.
- **Consistency with ADR-008:** Mirrors the session boundary alert pattern — one
  notification per state transition, no repeated noise.

## Implementation Details

### 1. `src/kairos/scheduler.py`
- Added `lunch_break_alert_sent: bool` flag to `SessionState` to ensure the alert
  fires exactly once per lunch break window (no repeated messages every 60s).
- Added `is_lunch_break() -> bool` helper that returns `True` when the current IST
  time falls strictly between `session_1_end` and `session_2_start`.
- Wired into the session gate block of `run_cycle()`:
  ```python
  if is_lunch_break() and not state.lunch_break_alert_sent:
      state.lunch_break_alert_sent = True
      await notifier.post_lunch_break()
  elif not is_lunch_break():
      state.lunch_break_alert_sent = False  # reset for next day
  ```
- The flag resets automatically when the time moves outside the lunch window,
  ensuring it fires again correctly on the next trading day.

### 2. `src/kairos/notifier.py`
- Added `post_lunch_break()` method to the `Notifier` class.
- Posts to **both** `discord_webhook_url` (#environment) and
  `discord_health_webhook_url` (#system-check) so the trader sees it regardless of
  which channel they're watching.
- Message format:
  ```
  ⏸️ LUNCH BREAK — NO TRADING
  ──────────────────────────────────
  Session 1 ended at 11:45 IST
  Session 2 resumes at 13:00 IST

  Engine is idle. Do NOT trade during this window.
  Signals will resume automatically at next session.
  🕐 11:46 IST
  ```

## API Contracts / File Assignments
| File | Change |
|------|--------|
| `src/kairos/scheduler.py` | `lunch_break_alert_sent` flag, `is_lunch_break()`, wiring in `run_cycle()` |
| `src/kairos/notifier.py` | `post_lunch_break()` method |

## Definition of Done
- At 11:46 IST (first cycle after session 1 ends), a single lunch break alert is
  posted to both Discord channels.
- No duplicate alerts fire during the 11:45–13:00 window.
- At 13:00 IST, the existing session boundary alert fires normally (per ADR-008).
- The flag resets daily without manual intervention.
