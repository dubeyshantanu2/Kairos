# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Test Suite:** Built an exhaustive 19-assertion `pytest` suite simulating pure environment scores. Added dataset fixtures in `tests/conftest.py` covering Pydantic models.
- **Documentation:** Added `docs/integration.md` detailing the OpenClaw orchestrator context.
- **Documentation:** Added `docs/scoring_architecture.md` recording mathematical condition thresholds.
- **Architecture Records:** Initialized `directives/adr/` capturing initial system design choices (Supabase Bridge, IV Cap constraint).
- **Repo Tooling:** Included standard Python `.gitignore` and `.env.example`.

### Changed
- **Structure:** Relocated core execution modules into `src/kairos/` aligning strictly with `pyproject.toml` packaging standards.
