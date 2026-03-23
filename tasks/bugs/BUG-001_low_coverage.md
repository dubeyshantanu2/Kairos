# BUG-001: Project Line Coverage Sub-80%

**Date:** 2026-03-23
**Severity:** High (Blocks Merge)

## Description
The project's overall test line-coverage has fallen to **30%**, triggering an automatic failure of the QA gate. The current threshold defined in project standards requires >= 80%.

## Reproduction
1. Initialize the virtual environment.
2. Run `pytest --cov=src/kairos tests/`
3. Observe overall coverage percentage.

## Root Cause
The core architectural scoring mathematically evaluates accurately (`processor`, `engine`), but files invoking external I/O are completely untested:
- `db.py`
- `fetcher.py`
- `notifier.py`
- `scheduler.py`

## Required Action (Code Generator)
1. Add `pytest-asyncio` and `respx` or `pytest-httpx` to dev dependencies.
2. Create `tests/test_fetcher.py` and mock the Dhan API endpoints to return dummy JSON matching `OptionChainRow`.
3. Create `tests/test_notifier.py` and block actual webhook firings using mock patching.
4. Create `tests/test_db.py` to mock the Supabase client calls.
5. Ensure overall line coverage hits 80%.
