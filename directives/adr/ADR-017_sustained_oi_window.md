# ADR-017: Sustained OI Window and Noise-Reduction Alerting
**Date:** 2026-04-15
**Status:** Approved

## Problem Statement
The system currently alerts on every minute fluctuation in condition values (per ADR-015), leading to excessive Discord noise. Additionally, 1-minute OI data is highly volatile, making it difficult to distinguish between "noise" (limit order fills) and "sustained conviction" (institutional buildup).

## Decision
1.  **True 5-Minute Rolling OI Window:** We will adjust the OI lookback buffer to 6 cycles (T-0 to T-5) to calculate a true 5-minute rolling delta. This delta will be the basis for all OI Flow scoring.
2.  **Noise-Reduction Alerting (Reversing ADR-015):** We will stop alerting on every minor value change. Discord notifications will now only trigger when:
    - The overall **Environment Status** changes (GO ↔ CAUTION ↔ AVOID).
    - A specific **Condition Color/Emoji** changes (e.g., Momentum goes from YELLOW to GREEN).
    - The **OI Trend Phase** changes (e.g., Neutral to Short Buildup).
3.  **Detail String Comparison:** To detect OI Phase changes, the system will compare the "Phase label" portion of the condition detail string (the part before the `|` delimiter) rather than the entire string.

## Rationale
- **Higher Signal Density:** Every alert now represents a meaningful shift in market sentiment or opportunity, rather than just a digit update.
- **Improved Lead Indicator:** A 5-minute rolling OI buildup is a more reliable lead indicator for trend continuation than a 1-minute snapshot.
- **Trader Focus:** Reduces distraction during active trading while ensuring no critical "Setup" changes are missed.

## Component Changes
- `src/kairos/config.py`: Set `oi_lookback_cycles = 6`.
- `src/kairos/scheduler.py`: Refactor `conditions_changed` logic to compare status and phase labels.

## Definition of Done
- [ ] No Discord alerts for minor digit changes in condition values.
- [ ] Discord alerts successfully triggered for Color/Emoji changes.
- [ ] Discord alerts successfully triggered for OI Phase changes (e.g., Neutral → Long Buildup).
- [ ] OI math verified to use T-5 as the baseline.
- [ ] Tests updated and passing.
