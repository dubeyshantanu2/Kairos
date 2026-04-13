# ADR-011 — DTE-Scaled IV Trend Thresholds
**Date:** 2026-04-13
**Status:** approved
**Triggered by:** Live observation — IV Trend GREEN threshold (+1.5) is unreachable on normal trading days

## Problem Statement
The IV Trend condition (Condition 1) uses a single threshold `iv_change_green = 1.5` for all DTE values.
On normal NIFTY trading days, 15-minute IV changes rarely exceed +0.5. The user's best-ever reading was
+0.21 (YELLOW). This means:

- IV Trend is permanently RED (0/2) → permanent IV Cap → system can never reach GO status
- The 2 points allocated to IV Trend are dead weight
- The IV Cap functions as a permanent blockade instead of a safety valve

## Decision
Scale IV thresholds by Days-To-Expiry (DTE), following the exact same 3-tier pattern already
established by `score_gamma_theta()` in processor.py.

### Rationale
- On **DTE=0** (expiry day): IV naturally drifts downward due to maximum theta. A +0.2 reading
  is genuinely meaningful because it fights the natural drift. Mild contraction is expected behavior,
  not a crisis signal.
- On **DTE≥3** (early week): IV drift is more neutral. For multi-day option holds, genuine IV
  expansion (+0.5+) is needed to confirm premiums will hold.

### Thresholds

| DTE | GREEN (2/2) | YELLOW (1/2) | RED (0/2 + IV Cap) |
|-----|------------|-------------|---------------------|
| 0–1 (expiry) | > +0.2 | ≥ -0.5 | < -0.5 |
| 2 (mid-week) | > +0.3 | ≥ -0.2 | < -0.2 |
| ≥3 (early week) | > +0.5 | ≥ 0.0 | < 0.0 |

### IV Cap Behavior
No change to cap logic (`iv_capped = c1_iv.status == "RED"`). The cap simply fires less
frequently because RED is now calibrated to genuine crush events, not normal market drift.

## Alternatives Considered

1. **Simple recalibration** (single threshold: green=0.3, yellow=-0.3): Simpler but doesn't
   account for DTE-specific IV behavior. Rejected.
2. **Percentile-based dynamic thresholds**: Self-calibrating but needs 2+ weeks of data and
   adds DB dependency to a pure function. Deferred to Phase 2.

## File Assignments

| File | Change |
|------|--------|
| `src/kairos/config.py` | Replace `iv_change_green`/`iv_change_yellow` with 6 DTE-scaled values |
| `src/kairos/processor.py` | `score_iv_change()` accepts `dte: int`, selects threshold tier |
| `src/kairos/engine.py` | Pass `dte` to `score_iv_change(iv_buffer, dte)` |

## IV Cap Release Simplification

The old `iv_cap_release_threshold = 0.30` config value is **removed**. The cap now uses
the IV Trend's own GREEN status as the release gate:

- **Cap ON**: IV Trend scores RED (engine.py sets `iv_capped = True`)
- **Cap HOLD**: IV Trend is YELLOW but cap was previously active → keep capping
- **Cap OFF**: IV Trend scores GREEN → genuine expansion confirmed, release cap

This eliminates the contradiction where IV Trend could score GREEN (+0.25 on DTE=0)
but the cap stayed active because +0.25 < 0.30 (old release threshold).

**Hysteresis is preserved**: the cap doesn't flicker during YELLOW readings.
It only releases on confirmed GREEN, which is already DTE-scaled.

## Definition of Done
- [x] Config: DTE-scaled IV thresholds added, old single threshold removed
- [x] Config: `iv_cap_release_threshold` removed (obsolete)
- [x] Processor: `score_iv_change()` accepts `dte`, selects threshold tier
- [x] Engine: passes `dte` to `score_iv_change()`
- [x] Scheduler: IV cap release simplified to use GREEN status
- [x] Scheduler restarts cleanly
