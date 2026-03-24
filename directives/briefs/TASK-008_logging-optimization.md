# Problem Brief — TASK-008
**Date:** 2026-03-25
**Status:** draft

## Problem Statement (Original)
the logs/kairos.log in server is becomming to big, how can we optimize this logging?

## Problem Statement (Simplified)
The current logging configuration consumes excessive disk space due to high-verbosity `DEBUG` levels, verbose multi-line formatting of Discord messages, and time-only rotation.

## What We Know
- `loguru` is used for logging.
- `logs/kairos.log` is configured with `level="DEBUG"`, `rotation="1 day"`, and `retention="7 days"`.
- `Notifier._post` logs every outgoing Discord message with a very wide (50 chars) visual separator (━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━).
- The engine runs every 60 seconds, and the heartbeat runs every 300 seconds.
- Currently, the log file is ~605K after a relatively short run (less than a full day), implying several megabytes per day per session.

## What We Don't Know (Assumptions to Validate)
- Is the user seeing the disk actually fill up, or just noticing the file growth?
- Are they using `syslog` or `journalctl` in addition to the file log?

## Edge Cases Identified
- **Runaway Loops**: If the API fails constantly, it logs an "API WARNING" every few cycles, which could bloat logs if not suppressed.
- **Damping Alert Suppression**: We recently added noise reduction (ADR-007), but the *log statements* themselves might still be verbose.

## Contradictions Found
- None.

## Clarifying Questions (max 3)
1. Should we prioritize *readability* (pretty formatting) or *disk space* (compact logs) for the file output?
2. Do we need 7 days of retention for `DEBUG` level logs, or can we reduce it to 1-2 days and keep `INFO` for longer?
3. Would you like to switch to a size-based rotation (e.g., 50MB) to prevent disk overflow in error conditions?

## Recommended Next Step
→ Software Architect Agent (ADR-008 to design rotation and level filtering)
