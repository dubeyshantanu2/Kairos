# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
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
