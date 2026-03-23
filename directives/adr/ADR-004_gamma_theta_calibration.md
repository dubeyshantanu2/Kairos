# ADR-004: Gamma/Theta Scaling & Dhan API Calibration
**Date:** 2026-03-23
**Status:** Active

## Problem Statement
The `score_gamma_theta()` condition in `processor.py` was permanently scoring RED. The dual root causes were:
1. **Scale Mismatch:** Dhan API returns Gamma in per-point-squared index terms (e.g., 0.00132), making the original hardcoded thresholds (e.g., 0.10) roughly 1000x too large.
2. **Data Consistency:** The condition only read CE Greeks, making it vulnerable to single-side data artifacts.
3. **Cold-Start Handling:** At session open, Dhan can return `gamma=0.0`, which previously caused a silent RED score instead of being treated as a "warming up" or "not yet populated" state.

## Decision
1. **Recalibrate Thresholds:** Update `src/kairos/config.py` with realistic Dhan-scale thresholds.
2. **Averaged Greeks:** Refactor `score_gamma_theta()` to use `(CE + PE) / 2` for both Gamma and Theta.
3. **Enhanced Guarding:** Add an explicit guard for `gamma == 0` to return a `YELLOW` "data not yet populated" result.
4. **Precision Increase:** Increase calculation and report rounding to 6 decimal places to maintain visibility of small-scale ratios.

## Rationale
- **Accuracy:** The new thresholds (e.g., Green=0.00008 at DTE≥3) align with actual production data samples from Dhan.
- **Robustness:** Averaging CE and PE mitigates the impact of single-side glitches often seen in live option chains.
- **Clarity:** Explicitly flagging `gamma=0` as "not yet populated" prevents false-negative RED scores during the first few seconds of a session.

## Component Changes
- `src/kairos/config.py`: Threshold constants updated.
- `src/kairos/processor.py`: `score_gamma_theta()` logic refactored.
- `tests/test_processor.py`: Updated to use realistic Dhan-scale mock data.
- `tests/conftest.py`: `make_atm` fixture updated to support PE Greeks.

## Alternatives Considered
- **Normalization:** We considered multiplying incoming Greeks by 1000, but decided against it to keep the code's mathematical definitions consistent with the raw API data.

## Definition of Done
- [x] All 7 conditions pass `pytest` with realistic data.
- [x] Ratio values in Discord alerts show 6 decimal places.
- [x] Session-start `gamma=0` returns YELLOW.
