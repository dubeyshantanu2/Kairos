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
the gap between `session_1_end` and the start of the `session_2` warmup period. The alert is posted to **both**
the `#environment` and `#system-check` Discord channels.

Additionally, we are introducing a **15-minute warmup window** exclusive to Session 2. The engine will wake up 15 minutes before the official post-lunch trading session begins (at 12:45 IST) to pre-fill the data buffers. Session 1 remains unchanged, starting at 09:15 IST, as pre-market option data is unavailable.

**Rationale:**
- **Trader Safety:** Explicitly tells the trader not to trade during the dead zone.
  The last GO/CAUTION signal from session 1 becomes stale after 11:45 and must not
  be acted upon.
- **Observability:** Removes ambiguity about whether the engine is alive or crashed.
  The trader sees a clear "engine idle, will resume at 13:00" message.
- **Consistency with ADR-008:** Mirrors the session boundary alert pattern — one
  notification per state transition, no repeated noise.
- **Zero-Latency Post-Lunch Signals:** By starting the engine 15 minutes before session 2, the rolling buffers (Momentum, Move Ratio, etc.) will be perfectly populated the exact minute the session begins. This ensures the 13:00 IST cycle delivers an immediate, fully-scored signal rather than forcing the trader to wait until 13:15 for the buffers to warm up. Notifications are explicitly suppressed during this 15-minute data-gathering phase.

## Implementation Details

### 1. `src/kairos/scheduler.py`
- Added `lunch_break_alert_sent: bool` flag to `SessionState` to ensure the alert
  fires exactly once per lunch break window (no repeated messages every 60s).
- Added `is_lunch_break() -> bool` helper that returns `True` when the current IST
  time falls strictly between `session_1_end` and `session_2_start` **minus 15 minutes**.
- Updated `is_active_session()` to dynamically include the `max(candle_buffer_size, iv_change_lookback)` period before the configured `session_start` time.
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
- Updated `run_cycle()` to only invoke `notifier.post_environment_alert` if `state.warmup_complete` is `True`. This ensures the silent data-gathering phase remains truly silent.

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
| `src/kairos/scheduler.py` | `lunch_break_alert_sent` flag, `is_lunch_break()`, `is_active_session()`, alert suppression in `run_cycle()` |
| `src/kairos/notifier.py` | `post_lunch_break()` method |

## Definition of Done
- At 11:46 IST (first cycle after session 1 ends), a single lunch break alert is
  posted to both Discord channels.
- No duplicate alerts fire during the 11:45–12:45 window.
- At 12:45 IST, the system silently enters the warmup phase, fetching data without posting environment alerts.
- At 13:00 IST, the existing session boundary alert fires normally (per ADR-008), followed immediately by a fully scored market signal.
- The flag resets daily without manual intervention.
