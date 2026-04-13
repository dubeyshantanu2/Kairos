# ADR-010: Cycle-Level OI Delta Calculation

## Status
Proposed (2026-03-25)

## Context
The OI Flow condition in `processor.py` evaluates directional conviction by checking if CE or PE open interest is building (positive delta) or unwinding (negative delta).

Previously, the `fetcher.py` module calculated `oi_change` as a day-level delta: `current_oi - previous_day_close_oi`. During market hours, both CE and PE legs almost always accumulate positive OI relative to the previous day's close. This resulted in the scoring engine permanently seeing "both building" and returning a RED ("Confused") status, regardless of actual intra-cycle directional shifts.

## Decision
Move the `oi_change` calculation from the stateless `fetcher.py` to the stateful `scheduler.py`.

1. **State Management**: Add `oi_snapshot_buffer` to `SessionState` in `scheduler.py`. This is a `deque` that stores the `oi` values for every `(strike, option_type)` pair for the last N cycles (controlled by `settings.oi_lookback_cycles`).
2. **Delta Calculation**: In `run_cycle()`, after fetching the option chain, calculate `oi_change` for each row by subtracting the baseline values (the oldest snapshot in the buffer) from the current values. 
3. **Rolling Buffer**: On every cycle, push the current OI snapshot into the buffer. This ensures we are always comparing the current OI against the values from exactly 5 minutes ago (if lookback is 5), providing a dampened, more reliable trend.
4. **Reset Policy**: Clear the buffer in `reset_buffers()` whenever a session starts or the configuration (symbol/expiry) changes.
5. **Fetcher Role**: The fetcher returns raw API data and sets `oi_change` to 0, leaving delta calculation to the stateful scheduler.

## Rationale
- **Noise Reduction**: Single-cycle (1-minute) deltas can be extremely noisy or even zero due to API throttling or low volume. A multi-cycle (5-minute) lookback provides a smoother and more actionable trend of institutional conviction.
- **Accuracy**: It ensures the "OI Flow" condition detects sustained building/unwinding rather than momentary blips.
- **Separation of Concerns**: The fetcher remains stateless; the scheduler manages the temporal state required for delta calculations.

## Consequences
- **First Cycle Baseline**: The first cycle of any session will always show 0 delta for all rows (as there is no prior snapshot). This is acceptable as a clean baseline.
- **Memory Usage**: Storing one extra snapshot of the option chain in memory has negligible impact (typically < 100 rows).
- **In-Place Mutation**: Requires the `OptionChainRow` Pydantic model to be non-frozen (`frozen=False`) to allow the scheduler to update the delta before passing it to the engine.
