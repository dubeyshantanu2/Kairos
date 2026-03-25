# ADR-010: Cycle-Level OI Delta Calculation

## Status
Proposed (2026-03-25)

## Context
The OI Flow condition in `processor.py` evaluates directional conviction by checking if CE or PE open interest is building (positive delta) or unwinding (negative delta).

Previously, the `fetcher.py` module calculated `oi_change` as a day-level delta: `current_oi - previous_day_close_oi`. During market hours, both CE and PE legs almost always accumulate positive OI relative to the previous day's close. This resulted in the scoring engine permanently seeing "both building" and returning a RED ("Confused") status, regardless of actual intra-cycle directional shifts.

## Decision
Move the `oi_change` calculation from the stateless `fetcher.py` to the stateful `scheduler.py`.

1. **State Management**: Add `prev_oi_snapshot` to `SessionState` in `scheduler.py`. This dictionary stores the `oi` value for every `(strike, option_type)` pair from the most recent successful fetch.
2. **Delta Calculation**: In `run_cycle()`, after fetching the option chain, calculate `oi_change` for each row by subtracting the snapshot value from the current value.
3. **Reset Policy**: Clear the snapshot in `reset_buffers()` whenever a session starts or the configuration (symbol/expiry) changes.
4. **Fetcher Role**: The fetcher now faithfully returns raw API data and sets `oi_change` to 0, signaling that it is not responsible for delta calculation.

## Rationale
- **Accuracy**: Cycle-level delta (e.g., the change in the last 1 minute) provides a much more granular and accurate signal of immediate conviction than cumulative daily build.
- **Separation of Concerns**: The fetcher should remain stateless and focused on API interaction. State-dependent calculations like deltas belong in the scheduler/orchestrator which manages the session lifecycle.
- **Correctness**: This fix resolves the permanent RED ("Confused") status in production, allowing the scoring engine to detect intra-minute unwinding/building correctly.

## Consequences
- **First Cycle Baseline**: The first cycle of any session will always show 0 delta for all rows (as there is no prior snapshot). This is acceptable as a clean baseline.
- **Memory Usage**: Storing one extra snapshot of the option chain in memory has negligible impact (typically < 100 rows).
- **In-Place Mutation**: Requires the `OptionChainRow` Pydantic model to be non-frozen (`frozen=False`) to allow the scheduler to update the delta before passing it to the engine.
