# ADR-023: 15-Minute Rolling Window for OI Flow

**Date:** 2026-06-29  
**Status:** Active  

## Context
The ATM OI Flow (Condition 3) scoring engine previously evaluated institutional positioning using a **15-minute Anchored Window** (ADR-017). This window reset the OI baseline to zero at the start of every 15-minute block of the hour (e.g. 14:00, 14:15, 14:30), causing:
1. **Starting-Block Neutrality:** For the first few minutes of a new block, the accumulated OI change was forced to zero, causing the score to drop to RED (Neutral) and creating a transient signal gap.
2. **Alert Delay:** To minimize noise, alerts for OI Phase shifts were strictly gated to the 15-minute interval boundaries (`now_minute % 15 == 0`). This introduced up to a 14-minute delay in notifying the trader of true structural trend reversals.

The introduction of the **Rolling Consensus Filter** (ADR-021), which aggregates the last 8 minutes of 1-minute updates, successfully stabilized signal noise. With noise-filtering handled by the consensus layer, the fixed 15-minute block boundaries and alert gating are no longer necessary.

## Decision
We will migrate from a 15-minute fixed anchored block window to a continuous **15-Minute Rolling Window**:

1. **State Management:**
   - Remove `oi_anchor_snapshot` and `anchor_block` from `SessionState`.
   - Add `oi_snapshot_buffer` to `SessionState`, implemented as a `deque` of options chain snapshots with `maxlen = settings.oi_lookback_cycles`.
2. **Delta Calculation:**
   - Push the current options chain snapshot `{(strike, option_type): oi}` into the rolling buffer every cycle.
   - Calculate the `oi_change` for each strike relative to the oldest snapshot in the buffer (T-15 cycles ago).
3. **Configuration Scaling:**
   - Update `oi_lookback_cycles = 16` to represent a true 15-minute rolling lookback (T-0 to T-15).
   - Increase `candle_buffer_size = 20` to ensure the candle buffer has sufficient room for the 16-cycle lookback during evaluation.
4. **Alerting Optimization:**
   - Remove the `now_minute % 15 == 0` gating constraint from the OI Phase shift detection in `scheduler.py`.
   - Allow phase shift notifications to trigger in real-time as soon as the rolling consensus filter validates a stable trend change.

## Rationale
- **Seamless Continuity:** Eliminates the artificial "0-delta drop" at block boundaries, keeping the scoring active and accurate throughout the trading session.
- **Timely Alerts:** Realizes the full capability of the consensus filter (ADR-021). Alerts trigger immediately when a new trend stabilizes, rather than lagging until the next 15-minute mark of the hour.
- **Microstructure Alignment:** 15 minutes of rolling data is perfectly aligned with typical exchange option chain updates (3-minute broadcasts) and institutional charting practices.

## Consequences
- **Session Warmup:** The system requires a 15-minute warmup (16 cycles) on session start or restart to populate the buffer before scoring can begin.
- **Memory Footprint:** Holding 16 option chain dicts in memory is trivial (< 200 KB).
- **Test Integrity:** Existing tests are monkeypatched to retain `oi_lookback_cycles = 6` to preserve their original configurations without modification.
