# ADR-011: Move Ratio — Time-Horizon Scaling
**Date:** 2026-03-25
**Status:** Active

## Problem Statement
The `score_move_ratio()` condition in `processor.py` was permanently scoring RED (ratios in the 0.06–0.18 range) across all live signals.

The root cause was a **time-horizon mismatch**:
- **Implied Move:** The straddle price (`CE_ltp + PE_ltp`) represents the market's expected move over the *entire remaining life* of the option (e.g., 6 days at DTE=6).
- **Realized Move:** Measured over a rolling 15-minute window.

Dividing a 15-minute realized range by a multi-day implied move produces a ratio structurally near zero, regardless of actual market volatility, making the condition impossible to score GREEN.

## Decisions
1. **Apply Square-Root-of-Time Scaling:** Scale the implied move down to a 15-minute equivalent before computing the ratio.
   ```python
   trading_mins_per_day = 375  # 09:15–15:30 IST
   total_remaining_mins = max(dte, 1) * trading_mins_per_day
   scaling_factor = math.sqrt(15 / total_remaining_mins)
   implied_pct_scaled = (straddle / spot) * 100 * scaling_factor
   ```
2. **Standardize Workday:** Defined `375` minutes as the standard Indian equity trading day (09:15 to 15:30).
3. **Expiry Day Safety:** Used `max(dte, 1)` to prevent division by zero on expiry day (DTE=0).

## Rationale
- **Consistency:** Uses the same volatility scaling principle (square root of time) already established in `ADR-004` for Gamma/Theta normalization.
- **Accuracy:** Brings both the numerator (realized) and denominator (implied) to the same 15-minute observational window, making the ratio `> 1.0` a mathematically valid signal for underpriced volatility.
- **Stability:** Ensures the condition remains sensitive and accurate across different DTE levels (6 days vs. 1 hour).

## Component Changes
- `src/kairos/processor.py`: `score_move_ratio()` signature updated to accept `dte`; logic updated with scaling.
- `src/kairos/engine.py`: `evaluate()` updated to pass the inherited `dte` parameter.
- `tests/test_processor.py`: `test_score_move_ratio_green` updated with recalibrated inputs.
- `docs/scoring_architecture.md`: Updated description for Condition 6.

## Definition of Done
- [x] `score_move_ratio()` applies scaling.
- [x] DTE=6 simulation scores GREEN on realistic 15-min volatile moves.
- [x] Division by zero safety for DTE=0.
- [x] All 56 tests pass.
