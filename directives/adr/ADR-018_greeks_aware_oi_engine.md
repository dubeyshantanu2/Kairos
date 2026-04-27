# ADR-018: Greeks-Aware OI Flow Scoring Engine
**Date:** 2026-04-22
**Status:** Approved

## Problem Statement
While ADR-016 introduced phase-based scoring, it still relied on raw OI deltas which can be noisy and fail to capture institutional positioning. Specifically, it missed "Vega traps" (where options are bought into contracting IV), "NDE contradictions" (where price moves opposite to the net delta exposure), and "GEX pins" (where dealer hedging absorbs volatility).

## Decision
Upgrade Condition 3 (OI Flow) from a simple phase classifier to a comprehensive, priority-based Greeks-aware scoring engine.

### Advanced Metrics Integrated:
1. **GEX (Gamma Exposure)**: Detects if dealers are "pinning" a strike (absorbing moves) or "trending" (amplifying moves).
2. **NDE (Net Delta Exposure)**: Measures the directional bias of the option chain relative to spot price action.
3. **Vega Trap Detection**: Identifies aggressive buying into falling IV, which increases the probability of premium decay even if the direction is correct.
4. **PCR (Put-Call Ratio)**: Used as a secondary confirmation of broader market sentiment alignment.
5. **Theta Dominance**: Detects when time decay (theta burn) is the dominant force, discouraging long entries.

### Priority-Based Scoring Logic:
The logic follows a strict hierarchy to determine if a signal is valid:
1. **Vega Trap** (Highest Priority) → **RED (0 pts)**
2. **NDE Contradiction** → **RED (0 pts)**
3. **GEX Pin** → **RED (0 pts)**
4. **Neutral Phase** → **RED (0 pts)**
5. **Theta Dominance** (w/o NDE Confirm) → **RED (0 pts)**
6. **Unified Conviction** (GEX Trend + NDE Confirm + PCR Aligned) → **GREEN (1 pt)**

## Rationale
This upgrade aligns the scoring engine with professional derivatives desk logic. By prioritizing the "reasons to avoid" (GEX pins, Vega traps) over simple directional momentum, the system provides a much higher signal-to-noise ratio for the trader.

## Component Changes
- `src/kairos/processor.py`: Implemented logic in `score_oi_flow`.
- `src/kairos/engine.py`: Added computation of GEX, NDE, and Theta burn metrics.
- `src/kairos/config.py`: Added thresholds for the new Greek-aware engine.
- `tests/test_oi_flow.py`: Comprehensive test suite for all priority rules.

## Definition of Done
- [x] All 5 Greek-aware metrics integrated into `score_oi_flow`.
- [x] Priority ordering correctly implemented (Vega Trap > NDE > GEX).
- [x] Unit tests in `tests/test_oi_flow.py` pass with 100% coverage for new logic.
- [x] Documentation updated in `README.md` and `scoring_architecture.md`.
