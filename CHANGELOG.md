# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **Move Ratio — Time-Horizon Scaling (`processor.py`, `engine.py`):**
  - Root cause: The implied move (straddle price) represented the expected move over the remaining life of the option (e.g., 6 days), while the realized move was measured over 15 minutes. This structural mismatch caused the ratio to be permanently RED (0.06–0.18 range).
  - Fix: Applied square-root-of-time scaling to the implied move to bring it down to a 15-minute equivalent before computing the ratio.
  - Added `max(dte, 1)` guard for division safety on expiry day.
  - Documented in `directives/adr/ADR-011_move_ratio_time_scaling.md`.
- **OI Flow — Cycle-Level Delta Implementation (`scheduler.py`, `fetcher.py`):**
  - Root cause: `fetcher.py` was returning a day-level OI delta (cumulative build since yesterday's close). This caused both legs (CE and PE) to always show positive build during market hours, leading to a permanent "Confused" (RED) scoring state.
  - Fix: Moved delta calculation to `scheduler.py`. The scheduler now maintains an in-memory `prev_oi_snapshot` and calculates the delta relative to the previous 1-minute cycle.
  - Removed day-level delta calculation from `fetcher.py` to ensure it remains a stateless API proxy.
  - Documented decision in `directives/adr/ADR-010_cycle_level_oi_delta.md`.
- **Initial Session Alert & Boundary Reset (`scheduler.py`):**
  - Root cause: The "proof of life" alert (introduced in ADR-008) only triggered if `previous_status` was `None`. However, the system failed to reset this status when crossing the lunch break boundary, causing the 1:00 PM session to start without an alert if the market status was unchanged from the morning.
  - Fix: Implemented `state.reset_buffers()` call within the session entry gate. This ensures `previous_status` is cleared, triggering the initial alert, and also flushes stale buffers between the morning and afternoon sessions.
  - Added regression test `test_run_cycle_session_transition_resets_state` to `tests/test_scheduler.py`.
- **Gamma/Theta Ratio — Theta Normalization (`processor.py`):**
  - Root cause: Dhan returns `theta` as an absolute ₹-per-day decay value (e.g. `-29.3`) while `gamma` is expressed per point² (e.g. `0.00047`). These are dimensionally incompatible, causing the raw `gamma / abs(theta)` ratio to always be near zero and score permanently RED.
  - Fix: `theta` is now normalized by the spot price (`theta_normalized = abs(theta) / spot_price`) before the ratio is computed. This converts theta to `₹-decay / point` (matching gamma's per-point² scale), yielding a meaningful ratio in the correct order of magnitude.
  - Updated `docs/scoring_architecture.md` and `directives/adr/ADR-004` to reflect the normalization step.
- **Scheduler Heartbeat:**
  - Suppressed heartbeats when no active session exists (returns `None` or status `STOPPED` from db).
  - Updated `run_heartbeat()` to call `db.get_active_session()` directly for live status.
- **Scoring Engine Calibration:**
  - Recalibrated `score_gamma_theta` thresholds by 1000x to match Dhan API's per-point-squared index terms.
  - Implemented CE/PE Greek averaging for robustness and added a session-open guard for `gamma=0` cases.
  - Increased reporting precision for ratios to 6 decimal places.
- **Dhan API Integration:** Resolved critical data fetching issues:
  - Corrected `/optionchain` endpoint payload (changed `UnderlyingSegment` to `UnderlyingSeg`) and response parsing for `data.oc` structure.
  - Fixed `/charts/intraday` by ensuring `securityId` is an integer and handling root-level OHLCV array responses.
  - Implemented smart index logic for `/charts/historical` to correctly identify the previous trading day when today's candle is (or isn't) present.
  - Corrected `/optionchain/expirylist` endpoint path and method.
- **Dhan Debugging:** Added detailed raw response logging for 4xx/5xx errors to speed up future troubleshooting.
- **Session Logic:** Removed temporary debug bypass flags and cleaned up verbose execution logging.
- **Test Suite:** 
  - Fixed `tests/test_fetcher.py` by aligning mock payloads with the actual nested `data.oc` API structure.
  - Updated `tests/test_processor.py` to use realistic Dhan-scale Greeks and added DTE-scaled boundary tests.
  - Built an exhaustive 49-assertion cumulative `pytest` suite ensuring all mathematical thresholds map to the correct 🟢/🟡/🔴 point system.
- **Documentation:** Added `ADR-004` documenting Gamma/Theta calibration decisions.
- **Documentation:** Updated `docs/scoring_architecture.md` with recalibrated thresholds.
- **Architecture Records:** Initialized `directives/adr/` capturing critical system design choices (Supabase Bridge, IV Cap, Greek Scaling).
- **Repo Tooling:** Included standard Python `.gitignore` and `.env.example`.

### Changed
- **Structure:** Relocated core execution modules into `src/kairos/` aligning strictly with `pyproject.toml` packaging standards.
