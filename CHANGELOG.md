# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **Dhan API Integration:** Resolved critical data fetching issues:
  - Corrected `/optionchain` endpoint payload (changed `UnderlyingSegment` to `UnderlyingSeg`) and response parsing for `data.oc` structure.
  - Fixed `/charts/intraday` by ensuring `securityId` is an integer and handling root-level OHLCV array responses.
  - Implemented smart index logic for `/charts/historical` to correctly identify the previous trading day when today's candle is (or isn't) present.
  - Corrected `/optionchain/expirylist` endpoint path and method.
- **Dhan Debugging:** Added detailed raw response logging for 4xx/5xx errors to speed up future troubleshooting.
- **Session Logic:** Removed temporary debug bypass flags and cleaned up verbose execution logging.
- **Test Suite:** Built an exhaustive 19-assertion `pytest` suite simulating pure environment scores. Added dataset fixtures in `tests/conftest.py` covering Pydantic models.
- **Documentation:** Added `docs/integration.md` detailing the OpenClaw orchestrator context.
- **Documentation:** Added `docs/scoring_architecture.md` recording mathematical condition thresholds.
- **Architecture Records:** Initialized `directives/adr/` capturing initial system design choices (Supabase Bridge, IV Cap constraint).
- **Repo Tooling:** Included standard Python `.gitignore` and `.env.example`.

### Changed
- **Structure:** Relocated core execution modules into `src/kairos/` aligning strictly with `pyproject.toml` packaging standards.
