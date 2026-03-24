# ADR-004: Gamma/Theta Scaling & Dhan API Calibration
**Date:** 2026-03-23
**Status:** Active (Amended 2026-03-24)

## Problem Statement
The `score_gamma_theta()` condition in `processor.py` was permanently scoring RED. The root causes were:
1. **Scale Mismatch:** Dhan API returns Gamma in per-point-squared index terms (e.g., `0.00132`), making the original hardcoded thresholds (e.g., `0.10`) roughly 1000x too large.
2. **Data Consistency:** The condition only read CE Greeks, making it vulnerable to single-side data artifacts.
3. **Cold-Start Handling:** At session open, Dhan can return `gamma=0.0`, which previously caused a silent RED score instead of a "warming up" / "not yet populated" state.
4. **Theta Dimensional Mismatch (discovered 2026-03-24):** Even after recalibrating thresholds, live production data showed the ratio was always near zero. Root cause: Dhan returns `theta` as an **absolute ₹-per-day decay** (e.g., `-29.3`), while `gamma` is expressed per point² (e.g., `0.00047`). These units are incompatible — computing `gamma / abs(theta)` directly destroys the signal.

## Decisions

1. **Recalibrate Thresholds:** Updated `src/kairos/config.py` with realistic Dhan-scale thresholds aligned to observed production Greek values.
2. **Averaged Greeks:** Refactored `score_gamma_theta()` to use `(CE + PE) / 2` for both Gamma and Theta for robustness against single-side data glitches.
3. **Enhanced Guarding:** Added an explicit guard for `gamma == 0` to return YELLOW ("data not yet populated") instead of a false-negative RED.
4. **Precision Increase:** Rounding to 6 decimal places to keep small-scale Dhan ratios visible in logs and Discord alerts.
5. **Theta Normalization (2026-03-24):** Divide averaged `abs(theta)` by `atm.spot_price` before computing the ratio:
   ```python
   theta_normalized = abs(theta) / spot_price  # ₹/day → ₹/day per index point
   ratio = gamma / theta_normalized
   ```
   This brings theta to the same per-point scale as gamma, yielding a dimensionally meaningful ratio.

## Rationale
- **Accuracy:** Recalibrated thresholds match observed production samples from Dhan for Nifty/Sensex.
- **Robustness:** CE+PE averaging mitigates the single-side glitches common in live option chains near expiry.
- **Dimensional Correctness:** Normalization by spot price is the minimal, reversible transform that makes the ratio stable and independent of the absolute index level.
- **Threshold Stability:** An alternative of rescaling thresholds to compensate for raw theta was rejected — those thresholds would drift with every significant Nifty level change.

## Component Changes
- `src/kairos/config.py`: DTE-scaled threshold constants updated.
- `src/kairos/processor.py`: `score_gamma_theta()` refactored (averaging + guarding + theta normalization).
- `tests/test_processor.py`: Updated to use realistic Dhan-scale mock data with DTE-scaled boundary tests.
- `tests/conftest.py`: `make_atm` fixture updated to include PE Greeks.
- `docs/scoring_architecture.md`: Condition 4 description updated to document normalization step.

## Definition of Done
- [x] All 7 conditions pass `pytest` with realistic Dhan-scale data.
- [x] Ratio values in Discord alerts show 6 decimal places.
- [x] Session-start `gamma=0` returns YELLOW.
- [x] Theta normalized by spot price — ratio no longer near-zero in live production data (confirmed via `[GREEK DEBUG]` log: `strike=22700 gamma=0.00047 theta=-29.3 spot≈22700 → ratio≈0.364`).
